# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Task Manager

In-memory task management for video generation jobs.
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from loguru import logger

from api.config import api_config
from api.tasks.models import Task, TaskProgress, TaskStatus, TaskType
from api.tasks.persistence import TaskPersistence


class TaskManager:
    """
    Task manager for handling async video generation tasks
    
    Features:
    - In-memory storage (can be replaced with Redis later)
    - Task lifecycle management
    - Progress tracking
    - Auto cleanup of old tasks
    """
    
    def __init__(self, persistence: Optional[TaskPersistence] = None):
        self._tasks: Dict[str, Task] = {}
        self._task_futures: Dict[str, asyncio.Task] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        self._persistence = persistence
        if self._persistence:
            self._load_persisted_tasks()
    
    async def start(self):
        """Start task manager and cleanup scheduler"""
        if self._running:
            logger.warning("Task manager already running")
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("✅ Task manager started")
    
    async def stop(self):
        """Stop task manager and cancel all tasks"""
        self._running = False
        
        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Cancel all running tasks
        for task_id, future in self._task_futures.items():
            if not future.done():
                future.cancel()
                logger.info(f"Cancelled task: {task_id}")
        
        self._tasks.clear()
        self._task_futures.clear()
        logger.info("✅ Task manager stopped")
    
    def create_task(
        self,
        task_type: TaskType,
        request_params: Optional[dict] = None,
        display_name: str = "",
        flow_name: str = "",
        step_key: str = "",
        session_id: str = "",
        artifact_keys: Optional[list[str]] = None,
        retry_payload: Optional[dict] = None,
        source_kind: Optional[str] = None,
        source_fact_id: Optional[str] = None,
    ) -> Task:
        """
        Create a new task
        
        Args:
            task_type: Type of task
            request_params: Original request parameters
            
        Returns:
            Created task
        """
        task_id = str(uuid.uuid4())
        task = Task(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            request_params=request_params,
            display_name=display_name,
            flow_name=flow_name,
            step_key=step_key,
            session_id=session_id,
            artifact_keys=artifact_keys or [],
            retry_payload=retry_payload,
            source_kind=source_kind,
            source_fact_id=source_fact_id,
        )
        
        self._tasks[task_id] = task
        self._persist_task(task)
        logger.info(f"Created task {task_id} ({task_type})")
        return task
    
    async def execute_task(
        self,
        task_id: str,
        coro_func: Callable,
        *args,
        **kwargs
    ):
        """
        Execute task asynchronously
        
        Args:
            task_id: Task ID
            coro_func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
        """
        task = self._tasks.get(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return
        
        # Create async task
        async def _execute():
            try:
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now()
                self._persist_task(task)
                logger.info(f"Task {task_id} started")
                
                # Execute the actual work
                result = await coro_func(*args, **kwargs)
                
                # Update task with result
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.completed_at = datetime.now()
                task.duration_ms = _duration_ms(task.started_at, task.completed_at)
                self._persist_task(task)
                logger.info(f"Task {task_id} completed")
                
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.completed_at = datetime.now()
                task.duration_ms = _duration_ms(task.started_at, task.completed_at)
                self._persist_task(task)
                logger.error(f"Task {task_id} failed: {e}")
        
        # Start execution
        future = asyncio.create_task(_execute())
        self._task_futures[task_id] = future
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID"""
        return self._tasks.get(task_id)
    
    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 100
    ) -> List[Task]:
        """
        List tasks with optional filtering
        
        Args:
            status: Filter by status
            limit: Maximum number of tasks to return
            
        Returns:
            List of tasks
        """
        tasks = list(self._tasks.values())
        
        if status:
            tasks = [t for t in tasks if t.status == status]
        
        # Sort by created_at descending
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        
        return tasks[:limit]
    
    def update_progress(
        self,
        task_id: str,
        current: int,
        total: int,
        message: str = ""
    ):
        """
        Update task progress
        
        Args:
            task_id: Task ID
            current: Current progress
            total: Total steps
            message: Progress message
        """
        task = self._tasks.get(task_id)
        if not task:
            return
        
        percentage = (current / total * 100) if total > 0 else 0
        task.progress = TaskProgress(
            current=current,
            total=total,
            percentage=percentage,
            message=message
        )
        self._persist_task(task)

    def complete_task(self, task_id: str, result: Optional[dict] = None) -> Optional[Task]:
        """Mark a task completed synchronously."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        if not task.started_at:
            task.started_at = datetime.now()
        task.status = TaskStatus.COMPLETED
        task.result = result
        task.completed_at = datetime.now()
        task.duration_ms = _duration_ms(task.started_at, task.completed_at)
        self._persist_task(task)
        return task

    def fail_task(self, task_id: str, error: str, result: Optional[dict] = None) -> Optional[Task]:
        """Mark a task failed synchronously."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        if not task.started_at:
            task.started_at = datetime.now()
        task.status = TaskStatus.FAILED
        task.error = error
        task.result = result
        task.completed_at = datetime.now()
        task.duration_ms = _duration_ms(task.started_at, task.completed_at)
        self._persist_task(task)
        return task
    
    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a running task
        
        Args:
            task_id: Task ID
            
        Returns:
            True if cancelled, False otherwise
        """
        task = self._tasks.get(task_id)
        if not task:
            return False
        
        # Do not cancel already-terminal tasks
        if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            return False

        # Cancel future if running
        future = self._task_futures.get(task_id)
        if future and not future.done():
            future.cancel()
        
        # Update task status
        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now()
        task.duration_ms = _duration_ms(task.started_at, task.completed_at)
        self._persist_task(task)
        logger.info(f"Cancelled task {task_id}")
        return True
    
    async def _cleanup_loop(self):
        """Periodically clean up old completed tasks"""
        while self._running:
            try:
                await asyncio.sleep(api_config.task_cleanup_interval)
                self._cleanup_old_tasks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    def _cleanup_old_tasks(self):
        """Remove old completed/failed tasks"""
        cutoff_time = datetime.now() - timedelta(seconds=api_config.task_retention_time)
        
        tasks_to_remove = []
        for task_id, task in self._tasks.items():
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                if task.completed_at and task.completed_at < cutoff_time:
                    tasks_to_remove.append(task_id)
        
        for task_id in tasks_to_remove:
            del self._tasks[task_id]
            if task_id in self._task_futures:
                del self._task_futures[task_id]
        if self._persistence:
            self._persistence.delete_tasks(tasks_to_remove)
        
        if tasks_to_remove:
            logger.info(f"Cleaned up {len(tasks_to_remove)} old tasks")

    def _load_persisted_tasks(self):
        self._persistence.mark_interrupted_tasks_failed()
        for task in self._persistence.load_tasks():
            self._tasks[task.task_id] = task

    def _persist_task(self, task: Task):
        if self._persistence:
            self._persistence.save_task(task)


# Global task manager instance
task_manager = TaskManager(TaskPersistence(os.getenv("PIXELLE_DESKTOP_TASKS_DB")))


def _duration_ms(started_at: Optional[datetime], completed_at: Optional[datetime]) -> int | None:
    if not started_at or not completed_at:
        return None
    return int((completed_at - started_at).total_seconds() * 1000)
