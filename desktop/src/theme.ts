import type { ThemeConfig } from "antd";

export type ThemeSkin = "graphite" | "warm" | "brand";

export type ThemeSkinConfig = {
  label: string;
  description: string;
  primary: string;
  bg: string;
  sidebar: string;
};

export const themeSkins: Record<ThemeSkin, ThemeSkinConfig> = {
  graphite: {
    label: "石墨蓝专业版",
    description: "默认专业工作台风格，适合长期生产使用。",
    primary: "#2F6FED",
    bg: "#F3F6FA",
    sidebar: "#172033",
  },
  warm: {
    label: "运营温度版",
    description: "更温暖的门店运营风格，适合老板和门店员工。",
    primary: "#D97706",
    bg: "#F7F8F5",
    sidebar: "#1F2933",
  },
  brand: {
    label: "品牌表现版",
    description: "更强强调色，适合需要品牌表现的生产环境。",
    primary: "#C2410C",
    bg: "#F5F6F8",
    sidebar: "#111827",
  },
};

export function createAntdTheme(skin: ThemeSkin): ThemeConfig {
  const selected = themeSkins[skin];
  return {
    token: {
      colorPrimary: selected.primary,
      colorBgLayout: selected.bg,
      colorBorder: "#DCE4EE",
      colorText: "#111827",
      colorTextSecondary: "#64748B",
      borderRadius: 10,
      fontFamily:
        'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    },
    components: {
      Button: {
        controlHeight: 38,
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
  if (value === "warm" || value === "brand" || value === "graphite") {
    return value;
  }
  return "graphite";
}
