// Desktop notifications from WSL via PowerShell toast notifications
// Falls back to console.log if PowerShell unavailable

import { execFileSync } from "child_process";

export function notify(title: string, body: string) {
  try {
    // Windows toast via PowerShell from WSL
    const script = `[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); $textNodes = $template.GetElementsByTagName('text'); $textNodes.Item(0).AppendChild($template.CreateTextNode('${title.replace(/'/g, "''")}')) > $null; $textNodes.Item(1).AppendChild($template.CreateTextNode('${body.replace(/'/g, "''").slice(0, 200)}')) > $null; $toast = [Windows.UI.Notifications.ToastNotification]::new($template); [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Molt.tui').Show($toast)`;
    execFileSync("powershell.exe", ["-NoProfile", "-Command", script], {
      encoding: "utf-8",
      timeout: 5000,
    });
  } catch {
    // Silent fallback — notification is nice-to-have, not critical
  }
}

export function copyToClipboard(text: string): boolean {
  try {
    execFileSync("powershell.exe", ["-NoProfile", "-Command", `Set-Clipboard -Value '${text.replace(/'/g, "''")}'`], {
      encoding: "utf-8",
      timeout: 3000,
    });
    return true;
  } catch {
    return false;
  }
}
