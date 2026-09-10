# 可复用凭据输入页

供本机桌面 Skill 配置 API Key、访问令牌等单行凭据。一个 Key 使用紧凑单输入框，多个 Key 在同页纵向排列，共用一个保存按钮。页面默认黑白灰，密钥只存系统凭据库。

## 适用范围

适合没有现成安全配置入口、需要用户首次填写或更换 API Key、访问令牌、Client Secret 的本机桌面 Skill。已有宿主凭据能力优先复用。

| 其他场景 | 使用方式 |
| --- | --- |
| OAuth、验证码或账号登录 | 服务官方授权流程 |
| 模型名、地址、目录等普通设置 | 普通配置文件或设置页 |
| 私钥文件、证书、多行密钥 | 专用凭据或文件授权机制 |
| CI、容器、远程服务器 | 已有 Secret 管理与可信运行时注入，不暴露本机输入页到网络 |

本组件减少密钥进入 Agent 对话和工具输出的机会，不是对同一用户下任意代码执行或浏览器控制的强隔离。

## 安装与单项配置

要求 Node.js 22.18+，以及下文对应系统凭据服务。首次下载依赖后，本地输入页可离线运行：

```bash
npm ci --ignore-scripts
npm run configure -- --label "服务 API Key" --title "输入密钥" --placeholder "粘贴你的密钥"
npm start
```

用户打开返回的本机链接，亲自填写并保存。默认字段文件为 manifests/default.json；configure 只修改非敏感声明，不接收密钥。支持 --dry-run 和 --save-label。

字段声明示例：

```json
{
  "version": 1,
  "id": "sample-skill",
  "label": "服务 API Key",
  "credential": "sample-skill/service/default",
  "ui": { "title": "输入密钥", "placeholder": "粘贴你的密钥", "saveLabel": "保存" }
}
```

id、label、credential 必填，ui 可省略。每项只接受非空单行密钥，最长 2500 个字符；系统后端的容量限制仍可能更低，失败时不会改存明文文件。密钥值不属于声明字段。

## 同页填写多个 Key

先创建另一项独立声明：

```bash
npm run configure -- --manifest manifests/image.json --id sample-skill --label "图片服务 API Key" --credential sample-skill/image/default --placeholder "粘贴图片服务密钥"
```

临时组合：

```bash
npm start -- --manifest manifests/default.json --manifest manifests/image.json
```

可复用页面配置：

```bash
npm run configure-page -- --page manifests/setup.page.json --manifest manifests/default.json --manifest manifests/image.json --title "连接服务" --label "两项服务" --save-label "保存"
npm start -- --page manifests/setup.page.json
```

页面 JSON 只保存引用与文案：

```json
{
  "version": 1,
  "manifests": ["default.json", "image.json"],
  "ui": { "title": "连接服务", "label": "两项服务", "saveLabel": "保存" }
}
```

每页 1 至 16 项，顺序由 manifests 决定。文件内的路径相对于页面配置文件，CLI 参数路径相对于运行目录。配置命令自动转换为相对路径；支持三端搬移。

只改页面文案：

```bash
npm run configure-page -- --page manifests/setup.page.json --title "配置服务"
```

不传 --manifest 保留列表，传入时替换整组。支持 --dry-run。字段标签和占位文字继续由 configure 修改；同页标题与按钮来自页面 ui。修改配置后重新启动。--page 和启动时的 --manifest 互斥。

已有字段声明的 id 与 credential 不可直接改写；新账号另建声明，不同账号使用不同引用。移除页面字段只改变表单，不删除系统凭据。

## 保存与恢复

尚未配置项必填；已有项显示“已配置”，留空保留，输入新值才替换。原值不会回填页面。替换按钮固定显示“替换并保存”，自定义文案不能覆盖这一提示。

整组预检通过后顺序保存。系统凭据库没有跨项事务：中途失败保留成功项、停止后续写入，并逐项标明结果，不自动回滚。用户先核对状态，再补填未完成项；后端报错可能存在结果不确定的情况，不能据此断言未写入。

提交结束或离开页面会清空输入。会话 30 分钟有效，全部成功后保留结果 90 秒。取消和过期不撤销此前保存。网络超时后先查状态，不重复提交。

Agent 只处理入口与脱敏状态，不自动操作含真实密钥的页面。/agent/status 使用启动令牌认证；只有 saved 表示全部成功，partial 表示部分失败。不要分享本机会话链接或让用户将密钥贴进聊天。

## 存储与平台

| 平台 | 后端 | 前提与管理入口 |
| --- | --- | --- |
| macOS | Keychain 钥匙串 | 当前用户钥匙串可访问；“钥匙串访问”中管理，系统授权由用户确认 |
| Windows | Credential Manager 凭据管理器 | 当前用户会话可用；“凭据管理器 → Windows 凭据”中的对应通用凭据 |
| Linux | secret-tool / Secret Service | libsecret 工具、用户 D-Bus 会话及已解锁的 Secret Service 实现，例如 GNOME Keyring；管理入口依桌面环境而定 |

macOS / Windows 通过 @napi-rs/keyring 原生绑定。Linux 显式调用 secret-tool，保存值经标准输入传递，不使用可能降级到临时 keyutils 的默认绑定。

服务标识为 org.oiloil.skill-credentials，账号属性为声明的 credential。不同后端界面显示名称可能不同。存储属于当前系统用户，本组件不负责跨设备同步、备份或迁移旧文件。

凭据库不可用或被锁定时停止，明确提示检查服务；不自动安装、解锁或降级到 JSON、浏览器存储等明文介质。服务器、无桌面 Linux 或其他凭据实现必须另行确认实际能力。

当前 macOS 已验证；Windows / Linux 已实现适配但尚未实机验证。

## 业务使用

把真实可信程序与环境变量名代入：

```bash
node src/run.ts --manifest manifests/default.json --env SERVICE_API_KEY -- your-program your-arguments
```

一次任务读取多个 Key：

```bash
node src/run.ts --manifest manifests/default.json --env FIRST_API_KEY --manifest manifests/image.json --env SECOND_API_KEY -- your-program your-arguments
```

全部读取成功后才启动程序，重复变量或缺少凭据时停止。页面文件只定义填写方式，业务端仍逐项绑定，避免注入不需要的密钥。密钥不进入命令参数或父进程环境。

包装器不是沙箱：可信子进程取得原值后仍可能打印或外传。需要强隔离时使用独立可信执行服务或宿主权限边界，不依赖密码框或系统凭据库作绝对保证。

检查单项状态：

```bash
npm run status -- --manifest manifests/image.json
```

仅返回配置状态与后端；未配置退出码 2，后端失败退出码 1。可信 Node.js 程序也可内部使用 nativeBackend 的 get / set / delete；保存与删除须用户授权，不向 Agent 暴露任意读取或删除接口。

## 开发验收

```bash
npm run check
npm run build
npm test
npm run test:native
```

常规测试使用假后端与受控 DOM，不操作真实浏览器。原生测试经真实同页 HTTP 入口写入随机假凭据，检查多变量业务读取与隔离，最后清理测试项。修改前端后必须提交一致的 public/app.js，最终用户无需编译。

维护时同时验证单 Key、同页多 Key、留空保留、部分失败重试、未知字段拒绝、会话隔离、状态脱敏及系统后端。不能用另写的静态演示替代正式页面测试。

## 固定业务入口

`manifests/profiles.json` 只保存业务名、声明文件和环境变量，不保存密钥。目标 Skill 接入时提供实际配置名；单项或多项复用相同页面与运行器：

```bash
node src/profile.ts status default
node src/profile.ts setup default
node src/profile.ts run default -- your-program your-arguments
```

status 退出码 0 表示所需凭据可读取，2 表示缺失，1 表示后端或配置错误。setup 由用户亲自填写；run 优先复用运行时环境变量，缺失时仅读取对应声明，不把其他服务凭据注入任务。指定其他服务时同时修改业务参数，不能只换凭据。
