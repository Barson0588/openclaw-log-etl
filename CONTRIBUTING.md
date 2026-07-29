# 参与贡献

感谢你考虑为这个项目花时间 🙏

## 基本规则

- **别客气**：没有大厂 code review 那套。改了能用就行
- **先提 issue 再写代码**：免得你花了时间写的功能我不打算加（或者已经在做了）
- **commit message 随意**：一个人维护，中英文都行，看得懂就行

## 提 PR

1. fork 仓库
2. 从 `main` 拉分支，命名随意（`fix-xxx`、`add-xxx` 都行）
3. PR 描述写两句改了啥
4. 提 PR

没了。

## 代码风格

保持和现有代码一致就行，没严格规范。几个约定：

- Python: 4 空格缩进，小写下划线
- JS: `const`/`let`，不用 `var`
- 一个 PR 只干一件事

## 本地开发

```bash
git clone <your-fork>
cd openclaw-log-etl
pip install -r requirements.txt
# mock 数据测试
./run.sh
# 有真实 OpenClaw 数据
./run.sh --real
```

## 加新的分析维度

1. 在 `analyzer.py` 加分析函数
2. 在 `report_generator.py` 里注册新的图表 section
3. 在 `client/` 里加对应的前端渲染逻辑
4. 在 `templates/` 里加页面模板（如果需要新页面）

## 有疑问？

直接提 issue 或者在 PR 里 @ 我。别不好意思。
