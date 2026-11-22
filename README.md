# 校园助教工时口径对账

`campus-ta-hours` 是面向东澜大学教务处的助教工时核算应用。它把课程班排班、签到、助教填报、教师审批和学院月报串成一条可追溯的工时口径链路。

## 真实场景

东澜大学有 6 个学院、约 180 个课程班，每月由助教在共享表格中填报工时，授课教师在邮件中确认，学院教务秘书再手工透视汇总。现有流程的痛点是排班与签到不一致时无法快速定位、不同课程的“有效工时”口径不一致、未审批记录容易被误计入月报。

上游输入是课程排班表、门禁签到和助教工时填报。系统替代排班签到核对、工时口径校验、教师审批和学院月报透视这四段工作。下游消费者是学院教务秘书、教学副院长和财务助学金核算人员。

## 主要功能

- 排班签到：按课程班展示当天排班窗口，登记签到/签退，并对跨时段或缺签记录转人工复核。
- 助教填报：助教提交活动类型、工作说明和自报工时，后端根据签到时长和课程口径计算有效工时。
- 教师审批：教师按课程班查看待审记录，审批、退回或将冲突记录转人工复核。
- 学院月报：按学院、课程班、活动类型、助教四个维度透视汇总，仅纳入已审批工时，可下载 JSON 快照。
- JWT 三角色：`ta` 助教、`teacher` 任课教师、`college_admin` 学院教务管理员。
- 审计与限流：审批、复核、月报发布均写入审计日志，API 对单用户请求进行简单窗口限流。

## 主流程与异常分支

主流程为 `签到 → 工时填报 → 教师审核 → 学院透视月报`。

- 签到时间必须落在课程排班窗口前后 30 分钟的容差内，且签到日期必须与课程排班星期匹配。
- 签到与排班冲突时，记录状态为 `manual_review`，教师不能直接审批，必须由学院管理员复核后再进入审批。
- 同一助教在不同学院的签到时段真实重叠时，并发审批也只有一笔进入计薪（`approved`），另一笔转为 `adjudication_pending` 并由冲突案例留痕，留待学院管理员裁决。
- 学院管理员可填理由改选计薪方：所选记录升为 `approved`、另一笔降为 `adjudication_pending`，同一事务内重算涉及学院的月报预览，两院结果一起更新；任一步失败整体回滚，原决定保持不变。
- 裁决接口支持 `Idempotency-Key`（或请求体 `idempotency_key`）：回执丢失时重试返回原回执并标记 `replayed`，不重复记账；若之后已有新裁决，重试返回 `superseded: true` 与当前赢家，不覆盖后来的决定。`expected_version` 不一致时返回 409 并保留现状。
- 审批与月报页面展示冲突的两笔记录、各自学院与有效工时、当前计薪方，以及每次裁决的操作人、所选记录和理由。
- 未审核工时的 `validated_hours` 不计入学院月报。
- 课程班月报只能由学院管理员生成，发布前会重新按数据库中的 `approved` 记录计算。

## 演示账号

密码统一为 `campus123`。

| 邮箱 | 角色 | 典型权限 |
|---|---|---|
| `ta@donglan.edu` | 助教 `ta` | 查看课程班、签到、创建和提交自己的工时填报 |
| `teacher@donglan.edu` | 教师 `teacher` | 查看所授课程班、审批或退回工时、处理待复核记录 |
| `admin@donglan.edu` | 学院管理员 `college_admin` | 维护排班、人工复核冲突、生成和发布学院月报 |

## 技术栈与服务

| 服务 | 技术 | 责任 |
|---|---|---|
| frontend | Nginx + 原生 HTML/CSS/JS | 页面、导航和 API 交互 |
| backend | Python 3.12 + FastAPI + psycopg | JWT、领域规则、工时校验、透视汇总 |
| worker | Python 3.12 | 共享卷心跳，模拟月报异步任务存活 |
| db | PostgreSQL 16 | 领域数据与审计日志 |
| redis | Redis 7 | 限流计数与缓存心跳 |

## 快速启动

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```

前端访问 `http://localhost:18254`，后端文档访问 `http://localhost:19254/docs`。

停止并清理测试数据：

```bash
docker compose down -v --remove-orphans
```

## 目录说明

- `backend/src/models` 领域表结构与数据库初始化
- `backend/src/services` 工时校验、月报透视、审计和认证
- `backend/src/routes` 认证、课程班、工时记录、月报接口
- `frontend/src/pages` 四个业务页面
- `backend/scripts/seed_demo.py` 幂等演示数据

## 共享枚举出现位置

- `WorkRecordStatus` 出现在 `backend/src/constants/enums.py`、`backend/src/schemas/work_records.py`、`frontend/src/constants/enums.js`。
- `AdjudicationCaseStatus` 出现在 `backend/src/constants/enums.py`、`frontend/src/constants/enums.js`。
- `UserRole` 出现在 `backend/src/constants/enums.py`、`backend/src/schemas/auth.py`、`frontend/src/constants/enums.js`。
- `ApprovalSheetStatus` 出现在 `backend/src/constants/enums.py`、`backend/src/schemas/reports.py`、`frontend/src/constants/enums.js`。

## 复现算法

工时有效值由 `min(签到签退实际分钟 / 60, 助教填报小时, 课程班单次口径上限)` 计算，四舍五入到 0.25 小时。排班冲突条件、缺签条件和有效小时口径写在 `backend/src/services/hour_policy.py`。月报透视按 `department × course_class × activity_type × ta` 聚合已审批记录，结果带 `approved_record_count`，便于财务复核。

跨学院重叠判定与裁决状态机写在 `backend/src/services/adjudication.py`：以 `ta_id` 的 PostgreSQL 事务级 advisory lock 串行化同一助教的审批与裁决，重叠加锁后重新读取状态，确保并发审批只有一笔计薪；冲突对按记录 id 归一化存入 `adjudication_cases`，每次改选连同理由、操作人与幂等键写入 `adjudication_decisions`。

- `GET /adjudications`、`GET /adjudications/{id}`：按角色可见范围返回冲突两笔记录、月报预览与全部裁决历史。
- `POST /adjudications/{id}/decisions`：学院管理员改选计薪方，`Idempotency-Key` 请求头（或 `idempotency_key` 字段）保障安全重试，`expected_version` 做乐观并发校验。

集成测试：`backend/tests/test_adjudication.py`（需本地 PostgreSQL，`DATABASE_URL` 指向可清空的测试库，`PYTHONPATH=backend pytest backend/tests`）。

## License

Internal demo for the Solo evaluation workspace.
