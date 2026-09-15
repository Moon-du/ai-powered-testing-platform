<script setup lang="ts">
const theme = {
  token: {
    colorPrimary: '#7c3aed',
    colorInfo: '#7c3aed',
    colorSuccess: '#10b981',
    colorWarning: '#f59e0b',
    colorError: '#f43f5e',
    borderRadius: 8,
    colorText: '#273142',
    colorTextSecondary: '#667085',
    colorBorder: '#e5e7eb',
    colorBgLayout: '#f5f6f8',
    colorBgContainer: '#ffffff',
    fontFamily:
      "Inter, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', system-ui, -apple-system, sans-serif",
  },
  components: {
    Button: {
      controlHeight: 34,
      primaryShadow: 'none',
    },
    Card: {
      headerFontSize: 15,
    },
    Menu: {
      itemBorderRadius: 7,
      itemHeight: 40,
      itemMarginInline: 12,
    },
  },
}
</script>

<template>
  <a-config-provider :theme="theme">
    <router-view />
  </a-config-provider>
</template>
