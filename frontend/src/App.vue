<template>
  <n-config-provider :theme="naiveTheme" :theme-overrides="themeOverrides" :locale="zhCN" :date-locale="dateZhCN">
    <n-global-style />
    <n-loading-bar-provider>
      <n-message-provider placement="top">
        <n-notification-provider placement="bottom-right">
          <n-dialog-provider>
            <UiBridge />
            <router-view />
          </n-dialog-provider>
        </n-notification-provider>
      </n-message-provider>
    </n-loading-bar-provider>
  </n-config-provider>
</template>

<script setup>
import { defineComponent } from 'vue'
import {
  NConfigProvider, NDialogProvider, NGlobalStyle, NLoadingBarProvider, NMessageProvider, NNotificationProvider,
  dateZhCN, useDialog, useLoadingBar, useMessage, useNotification, zhCN,
} from 'naive-ui'
import { naiveTheme, themeOverrides } from './composables/theme'
import { ui } from './api'

const UiBridge = defineComponent({
  setup() {
    ui.message = useMessage()
    ui.dialog = useDialog()
    ui.notification = useNotification()
    ui.loadingBar = useLoadingBar()
    return () => null
  },
})
</script>
