# API Key 配置与业务读取

已有宿主安全配置或可信运行环境注入时直接复用。首次在桌面填写或更换 Key 时使用随附统一页面，不能用“已支持环境变量”或终端隐藏输入代替页面接入。只为用户选择的外部服务配置；内置能力、离线处理和已有官方登录不要求额外 Key。

## 首次配置

将当前 SKILL.md 所在绝对目录记为 `SKILL_DIR`。页面需要 Node.js 22.18+，首次在组件目录安装锁定依赖：

```bash
npm --prefix "$SKILL_DIR/scripts/credential-ui" ci --ignore-scripts
node "$SKILL_DIR/scripts/credential-ui/src/profile.ts" status default
node "$SKILL_DIR/scripts/credential-ui/src/profile.ts" setup default
```

先查 status：退出码 0 表示当前业务凭据可读取，2 表示缺失，1 表示配置或系统后端失败。缺失或用户要求更换时才启动 setup，把返回的本机链接展示给用户，由用户亲自填写保存。不要自动操作真实 Key 页面，不让用户贴进聊天。

页面不回填原值；已有项留空保留，替换需要用户确认。只把 `saved` 当作全部保存成功；`partial`、超时和中断后先重新查状态，再补未完成项。配置成功仅证明保存和可读取，实际 API 可用性以业务调用为准。

## 服务与用途绑定

| 配置名 | 业务环境变量 | 系统凭据引用 |
| --- | --- | --- |
| default | `ZENMUX_API_KEY` | `oil-motion/zenmux/default` |

`default` 是脚本已有默认适配器，并不授权调用收费服务。用户选另一适配器时，同时选择对应配置名与业务参数，不能只换 Key。服务真实名称、接口和数据范围见原有依赖说明；以上变量名保留程序兼容。

一个服务的图片和视频共用同一 Key，不重复创建。多个服务各用独立声明；需要同页填写时用组件的 `configure-page` 组合所选声明，见[组件说明](../scripts/credential-ui/README.md)。不要求填写用户没有使用的服务。

## 运行业务

通过以下入口运行本 Skill 的真实脚本，`--` 后保留原业务参数：

完整业务命令见[提示词与提交](prompting.md)。执行时使用其中已包含的 `profile.ts run default` 包装器，并保留原业务参数。

环境变量优先；缺失时仅从系统库读取当前配置所需的 Key，并只注入可信业务子进程。参数、普通文件和状态输出都不含 Key。使用页面保存的凭据后，后续云端业务命令同样经 run 入口执行，不能只启动配置页后直接运行一个仍仅读环境变量的程序。视频提交的完整可执行示例只维护在[提示词与提交](prompting.md)，其中已使用 run 入口；不要复制或省略 Pilot/production 等必要参数。

系统后端分别为 macOS 钥匙串、Windows 凭据管理器、Linux Secret Service。Linux 需要 secret-tool、用户 D-Bus 和已解锁的桌面凭据服务；缺少后端时停止，不自动安装、解锁或降级明文。当前 macOS 组件有原生假凭据验证；Windows/Linux 适配仍需实机验收。CI、容器与远程服务器使用已有 Secret 注入，不把本机页面开放到网络。

原配置不自动迁移或删除；页面保存不代表旧明文文件已经清理。已有程序专用配置、账号或不同凭据引用按其原流程保留，不跨账号覆盖。凭据属于当前系统用户；正常流程不将其传入对话，不代表对同用户任意代码执行的强隔离。

## 验证

```bash
npm --prefix "$SKILL_DIR/scripts/credential-ui" run check
npm --prefix "$SKILL_DIR/scripts/credential-ui" run build
npm --prefix "$SKILL_DIR/scripts/credential-ui" test
```

测试使用假后端覆盖正式页面、同页 HTTP 保存、业务变量读取、部分失败恢复和脱敏；不操作用户真实页面。原生测试 `npm run test:native` 仅创建随机测试引用并清理，不验证实际服务额度或业务效果。
