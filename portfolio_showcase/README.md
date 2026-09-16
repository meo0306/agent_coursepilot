# CoursePilot Portfolio Showcase

CourseRAG × CoursePilot 的面试展示页。当前版本提供完整页面结构、滚动叙事、真实工程材料和确定性本地 Demo 结果回放。

页面公开内容整理自仓库根目录的 `showcase_materials/`，包括项目演进、架构边界、三类工作流、CourseRAG Dev 指标、P19 仓库验证结果和未通过的 P18 正式内容质量结论。

## 本地运行

需要 Node.js 20 或更高版本。

```powershell
npm.cmd install
npm.cmd run dev
```

生产构建与本地预览：

```powershell
npm.cmd run build
npm.cmd run preview
```

运行时不请求远程字体、图片、API 或模型服务。离线使用是指依赖安装和构建完成后，可以在无网络环境中通过本地静态服务器运行 `dist/`；不保证直接双击 `index.html` 的浏览器行为。

## 内容来源

页面结构化内容集中在 `src/content.ts`，并通过 `isPlaceholder` 保留未来待补材料的显式标记能力。当前首轮内容已全部替换为可追溯材料，不展示“示例内容”标签。

CourseRAG 指标仅适用于课程特定小规模 Dev 集；本地 Demo 证明工程链路，不代表实时模型或生产内容质量。P19 作品集发布 Gate 已通过，P18 正式内容质量 Gate 未通过。

## GitHub Pages

仓库工作流 `showcase-pages.yml` 只支持手动触发。首次发布前需要在 GitHub 仓库设置中将 Pages Source 设为 **GitHub Actions**，随后从 Actions 页面手动运行该工作流。

Vite 使用相对 `base`，因此构建产物可以部署到项目子路径，不需要硬编码仓库名。
