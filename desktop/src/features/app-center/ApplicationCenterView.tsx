import { AppstoreOutlined, FileTextOutlined, PictureOutlined, SoundOutlined, VideoCameraOutlined } from "@ant-design/icons";
import { Alert, Empty, Input, Tag, Typography } from "antd";
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
  statusTone: "success" | "processing" | "warning" | "default";
  enabled: boolean;
  routePath?: string;
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
  const statusLabel = ready ? "" : "待上线";
  const statusTone = ready ? "success" : "warning";
  const routePath = {
    "builtin.marketing-copy": "/apps/marketing-copy",
    "builtin.viral-titles": "/apps/viral-titles",
    "builtin.douyin-carousel": "/apps/douyin-carousel",
    "builtin.digital-human-video": "/apps/digital-human-video",
  }[manifest.app_id];
  return {
    appId: manifest.app_id,
    name: manifest.name,
    category: categoryLabels[manifest.category] || "运营提效",
    description: manifest.description,
    status: manifest.readiness.status,
    statusLabel,
    statusTone,
    enabled: manifest.enabled,
    routePath,
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
            按任务发现文案、标题、图文和视频能力；未准备好的应用会标记为待上线，最终平台发布始终保留人工确认。
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
              <article
                className={`app-center-card${ready ? " is-actionable" : ""}`}
                key={application.appId}
                role={ready ? "button" : undefined}
                tabIndex={ready ? 0 : undefined}
                aria-label={ready ? `打开${application.name}` : undefined}
                onClick={ready ? () => onOpenApp(application) : undefined}
                onKeyDown={ready ? (event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onOpenApp(application);
                  }
                } : undefined}
              >
                <div className="app-center-card-main">
                  <div className="app-center-card-copy-row">
                    <div className="app-center-card-icon"><Icon /></div>
                    <div className="app-center-card-copy">
                      <div className="app-center-card-heading">
                        <Typography.Title level={4}>{application.name}</Typography.Title>
                        <div className="app-center-card-tags">
                          <Tag color="default">{application.category}</Tag>
                          {application.statusLabel ? <Tag color={application.statusTone}>{application.statusLabel}</Tag> : null}
                        </div>
                      </div>
                      <Typography.Paragraph className="app-center-card-description" type="secondary">{application.description}</Typography.Paragraph>
                    </div>
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
