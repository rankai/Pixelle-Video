import { AppstoreOutlined, FileTextOutlined, PictureOutlined, SoundOutlined, VideoCameraOutlined } from "@ant-design/icons";
import { Alert, Button, Empty, Input, Tag, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";
import { listApplications, type ApplicationManifest } from "../../api";
import { featureFlags } from "../../featureFlags";

export type Application = {
  appId: string;
  name: string;
  category: string;
  description: string;
  status: ApplicationManifest["readiness"]["status"];
  statusLabel: string;
  enabled: boolean;
  routeView?: "ip" | "digital_human_app";
  actionable: boolean;
  keywords: string[];
  icon: typeof AppstoreOutlined;
};

const iconMap = {
  FilePenLine: FileTextOutlined,
  BadgeCheck: SoundOutlined,
  Images: PictureOutlined,
  Video: VideoCameraOutlined,
} as const;

const categoryLabels: Record<string, string> = {
  copywriting: "文案创作",
  carousel: "图文创作",
  video: "视频创作",
  operations: "运营提效",
};

const categories = ["全部", "文案创作", "视频创作", "图文创作", "运营提效"];

function toApplication(manifest: ApplicationManifest): Application {
  const backendReady = manifest.readiness.status === "ready" && manifest.enabled;
  const isDigitalHuman = manifest.app_id === "builtin.digital-human-video";
  const desktopReady = !isDigitalHuman || featureFlags.digitalHumanInAppCenter;
  const ready = backendReady && desktopReady;
  const statusLabel = isDigitalHuman && backendReady && !desktopReady
    ? "灰度未开启"
    : !manifest.enabled
    ? "未开启"
    : backendReady
      ? manifest.app_id === "builtin.digital-human-video" ? "可进入新流程" : "可用"
      : manifest.readiness.status === "not_ready" ? "需先完善配置" : "即将上线";
  return {
    appId: manifest.app_id,
    name: manifest.name,
    category: categoryLabels[manifest.category] || "运营提效",
    description: manifest.description,
    status: manifest.readiness.status,
    statusLabel,
    enabled: manifest.enabled,
    routeView: isDigitalHuman ? "digital_human_app" : undefined,
    actionable: ready,
    keywords: [manifest.app_id, manifest.feature_flag, manifest.category, ...manifest.required_capabilities],
    icon: iconMap[manifest.icon] || AppstoreOutlined,
  };
}

export function ApplicationCenterView({ onOpenApp }: { onOpenApp: (application: Application) => void }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("全部");
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    listApplications()
      .then((directory) => {
        if (!active) return;
        setApplications(directory.apps.map(toApplication));
        setError("");
      })
      .catch((reason) => {
        if (!active) return;
        setApplications([]);
        setError(String(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return applications.filter((application) => {
      const matchesCategory = category === "全部" || application.category === category;
      const haystack = [application.name, application.description, ...application.keywords].join(" ").toLowerCase();
      return matchesCategory && (!normalized || haystack.includes(normalized));
    });
  }, [applications, category, query]);

  return (
    <section className="app-center-page" aria-label="应用中心">
      <div className="app-center-intro">
        <div>
          <Typography.Text className="app-center-eyebrow">PIXELLE APPLICATION CENTER</Typography.Text>
          <Typography.Title level={2}>应用中心</Typography.Title>
          <Typography.Paragraph type="secondary">
            按任务发现文案、标题、图文和视频能力。目录和 readiness 由后端 Registry 提供，文案与标题应用已接入统一运行与版本链路。
          </Typography.Paragraph>
        </div>
        <Tag icon={<AppstoreOutlined />} color="processing">
          P0 应用中心
        </Tag>
      </div>

      {error ? <Alert type="warning" showIcon message="应用目录暂时不可用" description={error} /> : null}
      <div className="app-center-toolbar">
        <Input.Search
          allowClear
          aria-label="搜索应用"
          placeholder="搜索应用名称或能力"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="app-center-categories" role="tablist" aria-label="应用分类">
          {categories.map((item) => (
            <button
              key={item}
              type="button"
              role="tab"
              aria-selected={category === item}
              className={category === item ? "selected" : ""}
              onClick={() => setCategory(item)}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      {filtered.length ? (
        <div className="app-center-grid">
          {filtered.map((application) => {
            const Icon = application.icon;
            const ready = application.actionable;
            return (
              <article className="app-center-card" key={application.appId}>
                <div className="app-center-card-icon"><Icon /></div>
                <div className="app-center-card-main">
                  <div className="app-center-card-heading">
                    <Typography.Title level={4}>{application.name}</Typography.Title>
                    <Tag color={ready ? "success" : application.status === "disabled" ? "default" : "warning"}>
                      {application.statusLabel}
                    </Tag>
                  </div>
                  <Typography.Paragraph type="secondary">{application.description}</Typography.Paragraph>
                  <div className="app-center-card-footer">
                    <Typography.Text type="secondary">{application.category}</Typography.Text>
                    <Button type={ready ? "primary" : "default"} disabled={!application.actionable} onClick={() => onOpenApp(application)}>
                      {ready ? "打开流程" : "查看规划"}
                    </Button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <Empty description={loading ? "正在加载应用目录" : "没有匹配的应用"} />
      )}
    </section>
  );
}
