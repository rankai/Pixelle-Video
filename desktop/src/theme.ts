import type { ThemeConfig } from "antd";

export type ThemeSkin = "fresh" | "coral" | "graphite" | "warm" | "brand";

export type ThemeSkinConfig = {
  label: string;
  description: string;
  primary: string;
  bg: string;
  sidebar: string;
};

export const themeSkins: Record<ThemeSkin, ThemeSkinConfig> = {
  fresh: {
    label: "清新紫创作版",
    description: "清新柔和的创作工具风格，适合门店老板日常使用。",
    primary: "#6D5DF6",
    bg: "#F7F5FC",
    sidebar: "#FFFFFF",
  },
  coral: {
    label: "高效珊瑚工作台",
    description: "清晰、克制的企业视频工作台，突出当前任务和安全发布。",
    primary: "#F05A47",
    bg: "#F5F7FA",
    sidebar: "#FFFFFF",
  },
  graphite: {
    label: "石墨蓝专业版",
    description: "更稳重的蓝色版本，适合长期生产和团队协作。",
    primary: "#2F6FED",
    bg: "#F4F7FC",
    sidebar: "#FFFFFF",
  },
  warm: {
    label: "运营温度版",
    description: "更温暖的门店运营风格，适合老板和门店员工。",
    primary: "#D97706",
    bg: "#FFF8F1",
    sidebar: "#FFFFFF",
  },
  brand: {
    label: "品牌表现版",
    description: "更强强调色，适合需要品牌表现的生产环境。",
    primary: "#C2410C",
    bg: "#FFF7F3",
    sidebar: "#FFFFFF",
  },
};

export function createAntdTheme(skin: ThemeSkin): ThemeConfig {
  const selected = themeSkins[skin];
  return {
    token: {
      colorPrimary: selected.primary,
      colorBgLayout: selected.bg,
      colorBorder: "#E1E6ED",
      colorText: "#172033",
      colorTextSecondary: "#64748B",
      borderRadius: 10,
      fontFamily:
        'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    },
    components: {
      Button: {
        controlHeight: 40,
        borderRadius: 8,
      },
      Card: {
        borderRadiusLG: 14,
        paddingLG: 18,
      },
      Steps: {
        colorPrimary: selected.primary,
      },
    },
  };
}

export function readStoredThemeSkin(): ThemeSkin {
  const value = window.localStorage.getItem("pixelle_desktop_theme_skin");
  const migrated = window.localStorage.getItem("pixelle_theme_fresh_migrated");
  if (!migrated && value === "graphite") {
    window.localStorage.setItem("pixelle_desktop_theme_skin", "fresh");
    window.localStorage.setItem("pixelle_theme_fresh_migrated", "1");
    return "fresh";
  }
  if (!migrated) {
    window.localStorage.setItem("pixelle_theme_fresh_migrated", "1");
  }
  if (
    value === "fresh" ||
    value === "coral" ||
    value === "warm" ||
    value === "brand" ||
    value === "graphite"
  ) {
    return value;
  }
  return "fresh";
}
