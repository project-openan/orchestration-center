from framework.orchestration.model.psop import PSOP


MOCK_ES_WORKFLOW = """
# IG1526A AN L4无线能效优化解决方案包 v1.0.0

## 5.交互过程
基于上述功能架构和智能体/副驾驶的继承模型，本章重点阐述如何通过网络运维层和服务运维层智能体的交互与协作，实现无线能效优化的端到端处理。

### 5.1 AN L4无线能效优化交互流程

[图表: AN L4无线能效优化交互流程基于IAADE]

对于AN L4无线能效优化，RAN能效优化智能体以自主闭环模式运行，并与节能意图设置及效果评估智能体进行RAN域协调，包含两个阶段：

**RAN节能意图预评估阶段（步骤1-步骤3）**
- **步骤1** 表示RAN ES意图探索请求。该请求用于探索RAN ES意图目标（包括RAN能耗目标和RAN UE吞吐量）的最佳值。
- **步骤2** 表示评估和确定指定RAN ES意图目标的最佳可能值的探索过程，需考虑当前资源状况和系统能力。
- **步骤3** 表示获取RAN ES探索报告的响应，包含步骤1中所需目标的最佳可能值。

**RAN节能意图实现与评估阶段（步骤4-步骤9）**
- **步骤4** 表示RAN节能意图生成过程。在此过程中，根据RAN ES探索报告和运营商的业务需求生成RAN节能意图。不同频率或RAT(如4G、5G)在不同时段可分配不同的RAN UE吞吐量目标和RAN节能目标。
- **步骤5** 表示RAN ES意图的请求。
- **步骤6** 表示RAN ES意图实现的一系列流程，包括RAN ES数据收集、RAN ES分析、解决方案制定与执行（包括对RAN ES策略和对应RAN网元的操作配置活动）。
- **步骤7** 表示RAN ES效果评估及意图实现报告生成。RAN ES意图实现报告可能包含意图实现状态、达成值、对应意图目标的推荐值及RAN网元配置修改信息。
- **步骤8** 表示RAN ES意图实现报告的流程。
- **步骤9** 表示对不同RAN域的节能效果评估流程。根据节能效果评估结果，可能对RAN ES意图进行调整。

## 5.2 AN L4无线能效优化接口
在AN L4无线能效优化中，涉及以下接口列表：
|接口编号 | 接口名称 | 功能描述 |网络侧开放性| 参考接口标准文档|
|-------|-------|-------|-------|-------|
|网络-RAN ES智能体-API | RAN ES意图探索接口 | 1.RAN ES意图探索请求 <br> 2.RAN ES意图探索结果报告 |查看表7.1-3中的意图探索和3GPP TS 28.312第6.2.2节的RadioNetworkExpectation| https://portal.3gpp.org/desktopmodules/SpecificationDetails.aspx?specificationId=3554| 步骤1和步骤3 |
|        |RAN ES意图生命周期管理接口| 1.RAN ES意图创建<br>2. RAN ES 意图修改<br>3. RAN ES意图删除<br>4. RAN ES意图激活<br>5. RAN ES意图停用 |查看表7.1-1中的意图生命周期管理及3GPP TS 28.312第6.2.2节的2节的RadioNetworkExpectation |同上| 步骤5 |
|        |RAN ES意图报告接口 |1.查询意图报告<br>2. 订阅意图报告<br>3. 取消订阅意图报告<br>4. 通知意图报告| 查看7.1-2中的意图报告管理及3GPP TS 28.312第6.2.1.2.2节的IntentReport|同上|步骤8|
"""

mock_workflow_data = {
    "name": "test",
    "steps": [
        {
            "name": "step1",
            "type": "AllSuccess",
            "subtasks": [
                {
                    "agent": "Energy Saving Intent Agent",
                    "skill": "Intent Exploration Request",
                    "description": "RAN ES意图探索请求"
                },
            ],
            "next": [
                {
                    "step": "step2",
                    "condition": "探索请求成功提交"
                }
            ]
        },
        {
            "name": "step2",
            "type": "AllSuccess",
            "subtasks": [
                {
                    "agent": "RAN Energy Saving Agent",
                    "skill": "RAN ES Intent Exploration",
                    "description": "评估并确定RAN ES意图目标的最佳可能值"
                },
            ],
            "next": [
                {
                    "step": "step3",
                    "condition": "评估结果生成完成"
                }
            ]
        },
        {
            "name": "step3",
            "type": "AllSuccess",
            "subtasks": [
                {
                    "agent": "RAN Energy Saving Agent",
                    "skill": "RAN ES Intent Reporting",
                    "description": "获取RAN ES探索报告"
                },
            ],
            "next": [
                {
                    "step": "step4",
                    "condition": "探索报告获取成功"
                }
            ]
        },
        {
            "name": "step4",
            "type": "AllSuccess",
            "subtasks": [
                {
                    "agent": "Energy Saving Intent Agent",
                    "skill": "Intent Generation",
                    "description": "生成RAN节能意图内容"
                },
            ],
            "next": [
                {
                    "step": "step5",
                    "condition": "意图内容生成完成"
                }
            ]
        },
        {
            "name": "step5",
            "type": "AllSuccess",
            "subtasks": [
                {
                    "agent": "Energy Saving Intent Agent",
                    "skill": "Intent Delivery",
                    "description": "交付RAN ES意图请求"
                },
            ],
            "next": [
                {
                    "step": "step6",
                    "condition": "意图请求交付成功"
                }
            ]
        },
        {
            "name": "step6",
            "type": "AllSuccess",
            "subtasks": [
                {
                    "agent": "RAN Energy Saving Agent",
                    "skill": "RAN ES Intent Lifecycle Management",
                    "description": "执行RAN ES意图实现流程"
                },
            ],
            "next": [
                {
                    "step": "step7",
                    "condition": "意图实现流程执行完成"
                }
            ]
        },
        {
            "name": "step7",
            "type": "AllSuccess",
            "subtasks": [
                {
                    "agent": "RAN Energy Saving Agent",
                    "skill": "RAN ES Intent Reporting",
                    "description": "生成RAN ES意图实现报告"
                },
            ],
            "next": [
                {
                    "step": "step8",
                    "condition": "实现报告生成完成"
                }
            ]
        },
        {
            "name": "step9",
            "type": "AllSuccess",
            "subtasks": [
                {
                    "agent": "Energy Saving Intent Agent",
                    "skill": "Effect Evaluation",
                    "description": "评估不同RAN域节能效果并调整RAN ES意图"
                },
            ],
            "next": [
                {
                    "step": "end",
                    "condition": ""
                }
            ]
        }
    ]
}

mock_workflow = PSOP.model_validate(mock_workflow_data)
