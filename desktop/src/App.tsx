import { StudioApp } from "./StudioApp";
import { AppShell } from "./features/app-center/AppShell";

/**
 * Stable application entry. Product surfaces live in focused feature modules;
 * StudioApp owns orchestration for the five-stage production session.
 */
export function App() {
  return (
    <AppShell>
      <StudioApp />
    </AppShell>
  );
}
