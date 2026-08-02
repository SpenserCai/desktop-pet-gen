## 改动内容

<!-- 一两句话说明这个 PR 做了什么 -->

## 动机

<!-- 为什么需要这个改动？修复了什么问题、解决了什么需求？关联 issue 请写 Closes #123 -->

## 验证方式

<!-- 贴出你实际跑过的检查输出，而不是"应该没问题" -->

- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] `pytest -q`
- [ ] `cd pet-runtime && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test`
- [ ] `scripts/smoke_run.sh`（仅在改动运行时交互/UI 时必需）

```
<在此粘贴关键输出>
```

## 检查清单

- [ ] 改了行为就补了测试（修缺陷则补一个「没有这次修复就会失败」的测试）
- [ ] 没有编辑 `// GENERATOR-CONTRACT:` 锁定块（如需变更，已同步契约文档）
- [ ] 运行时 UI 文案仍是纯 ASCII
- [ ] 新增可调数值放在 `pet-runtime/src/config.rs`
- [ ] 用户可见的变更已加入 `CHANGELOG.md` 的 `Unreleased`
- [ ] 没有提交模型权重、构建产物或任何凭据

## 其他说明

<!-- 已知限制、后续计划、需要评审重点关注的地方 -->
