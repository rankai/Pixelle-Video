import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HashRouter, useHashRouter } from "./AppShell";

function RouteProbe() {
  const router = useHashRouter();
  return (
    <>
      <output aria-label="current route">{router?.pathname}</output>
      <button type="button" onClick={() => router?.navigate("/assets")}>资产</button>
      <button type="button" onClick={() => router?.navigate("/apps")}>离开发布中心</button>
      <button type="button" onClick={() => router?.navigate("/publish")}>返回发布中心</button>
    </>
  );
}

describe("HashRouter", () => {
  it("normalizes and navigates hash routes", async () => {
    window.localStorage.clear();
    window.location.hash = "#/unknown";
    render(<HashRouter><RouteProbe /></HashRouter>);

    await waitFor(() => expect(screen.getByLabelText("current route")).toHaveTextContent("/apps"));
    expect(window.location.hash).toBe("#/apps");
    fireEvent.click(screen.getByRole("button", { name: "资产" }));
    await waitFor(() => expect(screen.getByLabelText("current route")).toHaveTextContent("/assets"));
    expect(window.localStorage.getItem("pixelle_app_center_last_route")).toBe("/assets");
  });

  it("keeps the isolated digital-human route distinct from the legacy /ip route", async () => {
    window.localStorage.clear();
    window.location.hash = "#/apps/digital-human-video";
    render(<HashRouter><RouteProbe /></HashRouter>);

    await waitFor(() => expect(screen.getByLabelText("current route")).toHaveTextContent("/apps/digital-human-video"));
    expect(window.location.hash).toBe("#/apps/digital-human-video");
    expect(window.localStorage.getItem("pixelle_app_center_last_route")).toBe("/apps/digital-human-video");
  });

  it("accepts focused content-app workflow routes", async () => {
    window.localStorage.clear();
    window.location.hash = "#/apps/douyin-carousel";
    render(<HashRouter><RouteProbe /></HashRouter>);

    await waitFor(() => expect(screen.getByLabelText("current route")).toHaveTextContent("/apps/douyin-carousel"));
    expect(window.location.hash).toBe("#/apps/douyin-carousel");
  });

  it("preserves allowed publish handoff refs and rejects unknown query fields", async () => {
    window.localStorage.clear();
    window.location.hash = "#/publish?package_id=pkg_1&run_id=run_1";
    render(<HashRouter><RouteProbe /></HashRouter>);
    await waitFor(() => expect(screen.getByLabelText("current route")).toHaveTextContent("/publish?package_id=pkg_1&run_id=run_1"));
    expect(window.localStorage.getItem("pixelle_app_center_last_route")).toBe("/publish?package_id=pkg_1&run_id=run_1");
    window.location.hash = "#/publish?package_id=pkg_1&secret=bad";
    await waitFor(() => expect(screen.getByLabelText("current route")).toHaveTextContent("/apps"));
  });

  it("restores the canonical publish handoff after a refresh/restart simulation", async () => {
    window.localStorage.clear();
    window.location.hash = "#/publish?package_id=pkg_recovery&artifact_id=artifact_1";
    const first = render(<HashRouter><RouteProbe /></HashRouter>);
    await waitFor(() => expect(screen.getByLabelText("current route")).toHaveTextContent("/publish?package_id=pkg_recovery&artifact_id=artifact_1"));
    first.unmount();

    // Empty hash represents a fresh webview/Tauri document; the persisted
    // canonical handoff is the only recovery input and contains no local path.
    window.location.hash = "";
    render(<HashRouter><RouteProbe /></HashRouter>);
    await waitFor(() => expect(screen.getByLabelText("current route")).toHaveTextContent("/publish?package_id=pkg_recovery&artifact_id=artifact_1"));
    expect(window.localStorage.getItem("pixelle_app_center_last_route")).toBe("/publish?package_id=pkg_recovery&artifact_id=artifact_1");
  });

  it("keeps the package handoff when leaving and returning to the publish center", async () => {
    window.localStorage.clear();
    window.location.hash = "#/publish?package_id=pkg_leave_return";
    render(<HashRouter><RouteProbe /></HashRouter>);
    await waitFor(() => expect(screen.getByLabelText("current route")).toHaveTextContent("/publish?package_id=pkg_leave_return"));
    fireEvent.click(screen.getByRole("button", { name: "离开发布中心" }));
    await waitFor(() => expect(screen.getByLabelText("current route")).toHaveTextContent("/apps"));
    fireEvent.click(screen.getByRole("button", { name: "返回发布中心" }));
    await waitFor(() => expect(screen.getByLabelText("current route")).toHaveTextContent("/publish?package_id=pkg_leave_return"));
    expect(window.localStorage.getItem("pixelle_app_center_last_route")).toBe("/publish?package_id=pkg_leave_return");
    expect(window.localStorage.getItem("pixelle_app_center_last_publish_handoff")).toBe("/publish?package_id=pkg_leave_return");
  });
});
