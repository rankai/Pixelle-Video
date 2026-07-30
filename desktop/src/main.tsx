import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { initializeDesktopRuntime } from "./api";
import { applyRuntimeFeatureFlags } from "./featureFlags";
import "antd/dist/reset.css";
import "./styles.css";

async function bootstrap() {
  const runtime = await initializeDesktopRuntime();
  if (runtime) {
    applyRuntimeFeatureFlags(runtime.featureFlags);
  }
  ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}

void bootstrap();
