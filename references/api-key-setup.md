# API Key 配置与业务读取

生成关键帧和视频需要 ZenMux 的 API Key；处理已有素材不需要。运行环境已经可信地注入了 `ZENMUX_API_KEY`（例如 CI 或宿主的密钥配置）时直接复用。本机第一次填写或更换 Key 时，使用随附的本机配置页，不让用户把 Key 贴进聊天，也不改用终端输入。

## 首次配置

页面需要 Node.js 22.18+。第一次使用时在组件目录安装锁定依赖，然后查状态：

```bash
npm --prefix "$OIL_MOTION/scripts/credential-ui" ci --ignore-scripts
node "$OIL_MOTION/scripts/credential-ui/src/profile.ts" status default
node "$OIL_MOTION/scripts/credential-ui/src/profile.ts" setup default
```

`status` 的退出码：0 表示可以读取，2 表示还没配置，1 表示配置或系统凭据服务出错。只有缺失或用户要求更换时才运行 `setup`，把返回的本机链接交给用户亲自填写。不要自动操作真实的 Key 页面，也不截图。

页面不会回填已保存的值：已有项留空表示保留，替换前需要用户确认。只有返回 `saved` 才算全部保存成功；遇到 `partial`、超时或中断，先重新查状态，再补填未完成的项。保存成功只说明 Key 已存好、能读到，Key 是否有效以第一次生成调用的结果为准。

## 服务与用途绑定

| 配置名 | 业务环境变量 | 系统凭据引用 |
| --- | --- | --- |
| default | `ZENMUX_API_KEY` | `oil-motion/zenmux/default` |

图片和视频共用这一个 Key。配置好 Key 不代表可以随意调用收费接口：每次生成仍按主流程先做 Pilot，批量生成前让用户确认。

以后接入其他服务时，每个服务各写一份独立声明；需要在同一页填写时，用组件的 `configure-page` 组合，见[组件说明](../scripts/credential-ui/README.md)。不要求用户填写用不到的服务。

## 运行业务

`image_job.py` 与 `video_job.py` 都通过 `profile.ts run default --` 运行，`--` 后面照原样写业务参数。完整命令只维护在[提示词与提交](prompting.md)，不要在别处复制，也不要省略 Pilot、production 等必要参数。

环境变量优先；没有时，run 入口只从系统凭据库读取这个配置需要的 Key，并只注入给它启动的业务进程。命令参数、普通文件和状态输出里都不会出现 Key。页面保存的 Key 只能经 run 入口读到：直接运行生成脚本会报“读取不到 ZenMux API Key”，这时改用 run 入口，不要让用户重新填写。

## 平台与安全边界

系统凭据库分别是 macOS 钥匙串、Windows 凭据管理器和 Linux Secret Service。Linux 还需要 `secret-tool`、用户 D-Bus 和已解锁的桌面凭据服务。缺少后端时直接停止，不自动安装、解锁，也不改存明文。目前只在 macOS 上做过原生验证，Windows 和 Linux 还需要实机验收。CI、容器和远程服务器使用已有的密钥注入，不要把本机配置页开放到网络上。

旧版 `~/.config/oil-motion/config.json` 里的明文 Key 仍能被脚本读到，但不会被自动迁移或删除；用户在页面重新保存后，可以自己删掉旧文件。Key 属于当前系统用户，正常流程不会让它进入对话，但这不等于能防住同一用户下运行的任意程序。

## 验证

修改凭据组件后运行：

```bash
npm --prefix "$OIL_MOTION/scripts/credential-ui" run check
npm --prefix "$OIL_MOTION/scripts/credential-ui" run build
npm --prefix "$OIL_MOTION/scripts/credential-ui" test
```

测试用假后端覆盖页面、同页保存、业务变量读取、部分失败恢复和脱敏，不操作用户真实的 Key。原生测试 `npm run test:native` 只创建随机的测试条目并在结束后清理，不验证服务额度或生成效果。
