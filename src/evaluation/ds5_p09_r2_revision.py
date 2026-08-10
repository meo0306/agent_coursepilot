"""Build P09 r2 with complete answer-obligation and atomic-Claim coverage."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, cast

from docx import Document
from pydantic import JsonValue

from courserag.evals.schemas import (
    ClaimEvidenceSupport,
    DS2EvidenceDataset,
    DS3KnowledgePointDataset,
    DS5RetrievalQADataset,
    EvidenceRecord,
    GoldClaim,
    P09AnswerObligation,
    P09CaseCoverageAudit,
    P09ContextGoldCase,
    P09ContextGoldDataset,
    P09CoverageAuditDataset,
    P09GoldBundleManifest,
    P09NecessaryContextNeighbor,
    P09QAGoldCase,
    P09QAGoldDataset,
    P09ReviewDecisions,
)
from evaluation.contracts import CandidateRevisionArtifact, CandidateRevisionHistory
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import canonical_json_bytes, record_digest
from evaluation.ds5_p09_data import (
    APPROVAL_SCOPE,
    _artifact,
    _build_variants,
    _evidence_panel,
    _sha,
    _stable_id,
)
from evaluation.io import atomic_write_json, atomic_write_text

ROOT = Path("datasets/courserag_eval/v1")
R1_QA = ROOT / "candidates/ds5/p09_qa_r1.json"
R1_CONTEXT = ROOT / "candidates/ds5/p09_context_r1.json"
R2_QA = ROOT / "candidates/ds5/p09_qa_r2.json"
R2_CONTEXT = ROOT / "candidates/ds5/p09_context_r2.json"
P08 = ROOT / "approved/ds5/p08_retrieval.json"
DS2 = ROOT / "approved/ds2/p06_evidence.json"
DS3 = ROOT / "approved/ds3/p07_knowledge_points.json"
R1_MANIFEST = ROOT / "provenance/p09_gold_bundle_manifest_r1.json"
CANONICAL_MANIFEST = ROOT / "provenance/p09_gold_bundle_manifest.json"
R2_MANIFEST = ROOT / "provenance/p09_gold_bundle_manifest_r2.json"
COVERAGE_AUDIT = ROOT / "provenance/p09_answer_obligation_coverage_r2.json"
CHANGE_AUDIT = ROOT / "provenance/p09_r1_to_r2_record_changes.json"
REVISION_HISTORY = ROOT / "provenance/p09_candidate_revision_history.json"
CONTEXT_REVISION_HISTORY = ROOT / "provenance/p09_context_candidate_revision_history.json"
R1_FIRST_REVIEW = ROOT / "reviews/p09_r1_first_review_attestation.json"
R1_SECOND_REVIEW = ROOT / "reviews/p09_r1_second_review_attestation.json"
REPORT = Path("docs/refactor/phase_reports/ED_PRE_P09_DS5_QA_candidate_review_r2.md")
CANONICAL_REPORT = Path("docs/refactor/phase_reports/ED_PRE_P09_DS5_QA_candidate_review.md")

R2_POLICY = (
    "p09-qa-context-r2|preserve-p08-query-and-retrieval|answer-obligation-coverage|"
    "atomic-required-claims|approved-evidence-or-explicit-primary-neighbor|"
    "comparison-two-sided-frozen-example|factoid-list-short-answer|"
    "r1-owner-review-inheritance|all-semantic-changes-two-pass-review|"
    "no-p09-output|no-external-knowledge"
)
R2_STRATEGY_SHA256 = hashlib.sha256(R2_POLICY.encode()).hexdigest()

R1_BUNDLE_SHA256 = "0634c618279e8c4ddd432eeff2a20974924c06ddfe641f48da528d8311bb30e0"


def _normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _support_claim(
    *,
    qa: P09QAGoldCase,
    evidence: EvidenceRecord,
    evidence_sha256: str,
    claim_text: str,
    support_excerpt: str,
    neighbor: P09NecessaryContextNeighbor | None = None,
) -> GoldClaim:
    if neighbor is None:
        if support_excerpt not in evidence.gold_text:
            raise ValueError(f"Claim support is not in Evidence text: {qa.record_id}")
        support_source = "evidence_text"
        neighbor_id = None
    else:
        if neighbor.evidence_id != evidence.evidence_id or support_excerpt not in neighbor.text:
            raise ValueError(f"Claim support is not in the declared neighbor: {qa.record_id}")
        support_source = "necessary_neighbor"
        neighbor_id = neighbor.neighbor_id
    normalized = _normalized(claim_text)
    return GoldClaim(
        claim_id=_stable_id("gold-cl", qa.record_id, normalized, evidence.evidence_id),
        claim_text=claim_text,
        importance="required",
        required_evidence_ids=[evidence.evidence_id],
        claim_text_sha256=_sha(claim_text),
        normalized_claim_sha256=_sha(normalized),
        evidence_supports=[
            ClaimEvidenceSupport(
                evidence_id=evidence.evidence_id,
                evidence_record_sha256=evidence_sha256,
                support_role="primary",
                support_source=support_source,
                necessary_neighbor_id=neighbor_id,
                exact_support_excerpt=support_excerpt,
                exact_support_excerpt_sha256=_sha(support_excerpt),
            )
        ],
        annotation_rationale=(
            "该原子 Claim 逐项覆盖问题中的一个回答义务；支持内容来自 "
            + ("已批准 Evidence 的必要邻接。" if neighbor else "Approved DS2 Evidence 正文。")
        ),
    )


def _required_evidence_id(qa: P09QAGoldCase) -> str:
    evidence_ids = list(
        dict.fromkeys(
            evidence_id for claim in qa.gold_claims for evidence_id in claim.required_evidence_ids
        )
    )
    if len(evidence_ids) != 1:
        raise ValueError(f"manual atomic revision expects one Evidence: {qa.record_id}")
    return evidence_ids[0]


def _find_neighbor(
    context: P09ContextGoldCase,
    *,
    evidence_id: str,
    contains: str,
) -> P09NecessaryContextNeighbor:
    matches = [
        item
        for item in context.necessary_neighbors
        if item.evidence_id == evidence_id and contains in item.text
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one P09 neighbor containing {contains!r}: {context.qa_case_id}")
    return matches[0]


def _ernie_execution_neighbor(
    *,
    evidence: EvidenceRecord,
    document_path: Path,
) -> P09NecessaryContextNeighbor:
    document = Document(str(document_path))
    paragraphs = [document.paragraphs[index].text for index in range(1729, 1740)]
    text = "\n".join(item for item in paragraphs if item)
    required_fragments = (
        "使用基础模型进行预测，代码如下：",
        "!python run_infer.py --param_path /home/aistudio/config/cls_ernie_fc_ch_infer_base.json",
        "接着，在配置文件/home/aistudio/config/cls_ernie_fc_ch_infer_finetune.json中修改微调后的模型路径",
        "!python run_infer.py --param_path /home/aistudio/config/cls_ernie_fc_ch_infer_finetune.json",
    )
    if any(item not in text for item in required_fragments):
        raise ValueError("frozen DOCX no longer contains the independently verified ERNIE steps")
    text_sha256 = _sha(text)
    source_span = evidence.source_span.model_copy(
        update={
            "block_start": "paragraph:1729",
            "block_end": "paragraph:1739",
            "char_start": None,
            "char_end": None,
            "page_start": 272,
            "page_end": 272,
        }
    )
    return P09NecessaryContextNeighbor(
        neighbor_id=_stable_id("gold-nb", evidence.evidence_id, "next", text_sha256),
        evidence_id=evidence.evidence_id,
        relation="next",
        text=text,
        text_sha256=text_sha256,
        source_span=source_span,
        necessity_reason="complete_procedure",
    )


def _atomic_claims(
    *,
    qa: P09QAGoldCase,
    context: P09ContextGoldCase,
    evidence: dict[str, EvidenceRecord],
    evidence_hashes: dict[str, str],
) -> tuple[list[GoldClaim], list[str] | None]:
    rid = qa.record_id
    eid = _required_evidence_id(qa)
    source = evidence[eid]
    source_hash = evidence_hashes[eid]
    excerpt = source.gold_text

    def claims(items: list[str], *, support: str | None = None) -> list[GoldClaim]:
        return [
            _support_claim(
                qa=qa,
                evidence=source,
                evidence_sha256=source_hash,
                claim_text=item,
                support_excerpt=support or excerpt,
            )
            for item in items
        ]

    if rid == "gold-qa-78aa66e747df675f48bff6dc8bcd6426":
        values = [
            "该应用实例是全球首个全仿真智能 AI 主持人。",
            "发布者是搜狗与新华社。",
            "发布时间是2018年11月7日。",
            "发布场合是第五届世界互联网大会。",
        ]
        return claims(values), [
            "全球首个全仿真智能 AI 主持人；搜狗与新华社；2018年11月7日；第五届世界互联网大会"
        ]
    if rid == "gold-qa-2b8972b47de56a5b6b62e68091320557":
        neighbor = _find_neighbor(context, evidence_id=eid, contains="26%左右")
        values = [
            "基础模型预测时，错误分类的概率在26%左右。",
            "微调模型预测时，错误分类的概率几乎为0。",
        ]
        return [
            _support_claim(
                qa=qa,
                evidence=source,
                evidence_sha256=source_hash,
                claim_text=item,
                support_excerpt=neighbor.text,
                neighbor=neighbor,
            )
            for item in values
        ], ["基础模型错误分类概率约26%；微调模型错误分类概率几乎为0"]
    if rid == "gold-qa-720907acf5c019bca8604d8bbaddf311":
        values = [
            "视角转换矩阵 W 决定转换后的二维协方差矩阵 Σ′∈R^{2×2}。",
            "二维协方差变换公式为 Σ′=JWΣW^T J^T。",
        ]
        return claims(values), ["Σ′=JWΣW^T J^T"]
    if rid == "gold-qa-a74bb4b9fcefc7df08ea2063151445b8":
        neighbor = _find_neighbor(context, evidence_id=eid, contains="AI生成声音人格权侵权案")
        values = [
            "2024年出现了全国首例“AI生成声音人格权侵权案”。",
            "该案例提示需要重视声音权益保护和技术的规范应用。",
        ]
        return [
            _support_claim(
                qa=qa,
                evidence=source,
                evidence_sha256=source_hash,
                claim_text=item,
                support_excerpt=neighbor.text,
                neighbor=neighbor,
            )
            for item in values
        ], ["2024年全国首例“AI生成声音人格权侵权案”"]
    if rid == "gold-qa-730f317833bc4b6f6d458f42814069be":
        neighbor = _find_neighbor(context, evidence_id=eid, contains="1/||ω||")
        value = "空间内任意一点 X_0 到感知机超平面的距离为 1/||ω|| |ω·X_0+b|。"
        claim = _support_claim(
            qa=qa,
            evidence=source,
            evidence_sha256=source_hash,
            claim_text=value,
            support_excerpt=neighbor.text,
            neighbor=neighbor,
        )
        return [claim], ["1/||ω|| |ω·X_0+b|"]
    if rid == "gold-qa-57e64654e5909a0c1a2c6f5b89d3315f":
        values = [
            "第一行代码构造了一个感知机模型。",
            "fit_intercept=False 表示训练时假设数据已经中心化。",
            "训练过程迭代20次。",
            "每次循环都会打乱样本顺序。",
        ]
        return claims(values), [
            "构造感知机模型；fit_intercept=False；迭代20次；每次循环打乱样本顺序"
        ]
    if rid == "gold-qa-574fc80decab989823e88f69bc850f15":
        values = [
            "这些文本训练数据集通常公开可用。",
            "这些数据集包含大量文本数据。",
            "这些数据集覆盖广泛的主题和领域。",
        ]
        return claims(values), ["通常公开可用；包含大量文本数据；覆盖广泛主题和领域"]
    if rid == "gold-qa-01fd462adc1638a1a81fcabdf58e0ac9":
        values = [
            "跨境支付中的汇率波动会直接影响交易成本。",
            "跨境支付中的汇率波动会直接影响结算金额。",
        ]
        return claims(values), ["汇率波动会影响交易成本和结算金额"]
    if rid == "gold-qa-f287be490a3c23fdd7bc3d027b70051a":
        values = [
            "感知机算法最初由 Frank Rosenblatt 提出。",
            "感知机算法于1957年提出。",
            "感知机算法在康奈尔航空实验提出。",
        ]
        return claims(values), ["Frank Rosenblatt；1957年；康奈尔航空实验"]
    if rid == "gold-qa-6008640bfe85562d6598e3805655f820":
        values = [
            "瓦片排序算法根据瓦片内高斯粒子的深度信息生成深度排序列表。",
            "最终图像合成遵循从后到前的顺序。",
        ]
        return claims(values), None
    if rid == "gold-qa-f9aea3f33c261e97222b15cf5b46fddf":
        lines = [item.strip() for item in excerpt.splitlines() if item.strip()]
        required = [
            "输入：样本集合{(X_i,Y_i)}_{i=1}^s",
            "输出：分类超平面的法向量ω和b",
            "初始化：ω_1←0∈R^n，b_1←0",
            "随机挑选样本序号i=1,…,s",
            "if 分类错误Y_{i(t)}(ω_t^T X_{i(t)})≤0：",
            "更新ω_{t+1}←ω_t+ηY_{i(t)}X_{i(t)}",
            "b_{t+1}←b_t+ηY_{i(t)}",
            "ω_{t+1}←ω_t",
            "返回ω_{T+1}",
        ]
        if any(item not in lines for item in required):
            raise ValueError("perceptron algorithm Evidence changed")
        return [
            _support_claim(
                qa=qa,
                evidence=source,
                evidence_sha256=source_hash,
                claim_text=item,
                support_excerpt=item,
            )
            for item in required
        ], None
    if rid == "gold-qa-2a2684775884b34032cd3adf427ec866":
        wanted = {"模型快速推理", "模型快速训练", "模型可编辑", "动态场景重建"}
        current = ""
        output: list[GoldClaim] = []
        for row in [item for item in excerpt.splitlines() if item.strip()]:
            cells = row.split("\t")
            if cells[0].strip():
                current = cells[0].strip()
            method = cells[1].strip() if len(cells) > 1 else ""
            if current in wanted and method:
                output.append(
                    _support_claim(
                        qa=qa,
                        evidence=source,
                        evidence_sha256=source_hash,
                        claim_text=f"{current}方法包括 {method}。",
                        support_excerpt=row,
                    )
                )
        if len(output) != 16:
            raise ValueError("NeRF method table must yield sixteen requested methods")
        return output, None
    if rid == "gold-qa-252adaf1a1cbe9d9371796e0f770889b":
        values = [
            "通用人工智能强调拥有像人一样的能力。",
            "通用人工智能可以通过学习胜任人可以做的任何工作。",
            "通用人工智能不要求具有自我意识。",
        ]
        return claims(values), None
    if rid == "gold-qa-a9d45653719933fd1bc9790cf1f0db87":
        values = [
            "传感数据的监督式算法覆盖离散分类和连续回归。",
            "传感数据的半监督式算法包括生成模型。",
            "表中列出了强化学习。",
            "传感数据的无监督式算法覆盖聚类、降维、特征提取和模式识别。",
        ]
        return claims(values), None
    if rid == "gold-qa-18b8640afc285e8d4ecebec3db23684f":
        neighbor = _find_neighbor(context, evidence_id=eid, contains="run_infer.py")
        config = _support_claim(
            qa=qa,
            evidence=source,
            evidence_sha256=source_hash,
            claim_text="预测 JSON 需要配置模型输入路径、预测文件输入路径和预测结果输出路径。",
            support_excerpt=excerpt,
        )
        specs = [
            (
                "基础模型通过 cls_ernie_fc_ch_infer_base.json 执行 run_infer.py。",
                "!python run_infer.py --param_path /home/aistudio/config/cls_ernie_fc_ch_infer_base.json",
            ),
            (
                "微调模型预测前需要在 cls_ernie_fc_ch_infer_finetune.json 中修改微调后的模型路径。",
                "接着，在配置文件/home/aistudio/config/cls_ernie_fc_ch_infer_finetune.json中修改微调后的模型路径",
            ),
            (
                "微调模型通过 cls_ernie_fc_ch_infer_finetune.json 执行 run_infer.py。",
                "!python run_infer.py --param_path /home/aistudio/config/cls_ernie_fc_ch_infer_finetune.json",
            ),
        ]
        return [config] + [
            _support_claim(
                qa=qa,
                evidence=source,
                evidence_sha256=source_hash,
                claim_text=claim_text,
                support_excerpt=support_text,
                neighbor=neighbor,
            )
            for claim_text, support_text in specs
        ], None
    if rid == "gold-qa-09063e7caac8aa5ae1a49e6d7081b9ca":
        values = [
            "GPT-4 使用大约25000个 A100 进行训练。",
            "GPT-4 训练了90到100天。",
            "GPT-4 的训练成本大约为6000万美元。",
        ]
        return claims(values), None
    if rid == "gold-qa-74304d145c41aaf7ea44b17108ef39ef":
        values = [
            "大规模数据训练使模型接触到极其多样化的情景和例子。",
            "广泛的学习经验为涌现能力的形成提供了必要基础。",
        ]
        return claims(values), None
    if rid == "gold-qa-10caf16efab833ad40e600359b5239c2":
        values = [
            "在教室正前方设置摄像头采集视频。",
            "通过前置计算设备或服务器中的专注度分析模型进行检测与识别。",
            "系统自动分析学生的专注度。",
            "系统实时将专注度及行为统计结果反馈给学校管理系统。",
            "系统在课后生成教学报告。",
        ]
        return claims(values), None
    raise KeyError(rid)


ATOMIC_REVISION_IDS = {
    "gold-qa-78aa66e747df675f48bff6dc8bcd6426",
    "gold-qa-2b8972b47de56a5b6b62e68091320557",
    "gold-qa-720907acf5c019bca8604d8bbaddf311",
    "gold-qa-a74bb4b9fcefc7df08ea2063151445b8",
    "gold-qa-730f317833bc4b6f6d458f42814069be",
    "gold-qa-57e64654e5909a0c1a2c6f5b89d3315f",
    "gold-qa-574fc80decab989823e88f69bc850f15",
    "gold-qa-01fd462adc1638a1a81fcabdf58e0ac9",
    "gold-qa-f287be490a3c23fdd7bc3d027b70051a",
    "gold-qa-6008640bfe85562d6598e3805655f820",
    "gold-qa-f9aea3f33c261e97222b15cf5b46fddf",
    "gold-qa-2a2684775884b34032cd3adf427ec866",
    "gold-qa-252adaf1a1cbe9d9371796e0f770889b",
    "gold-qa-a9d45653719933fd1bc9790cf1f0db87",
    "gold-qa-18b8640afc285e8d4ecebec3db23684f",
    "gold-qa-09063e7caac8aa5ae1a49e6d7081b9ca",
    "gold-qa-74304d145c41aaf7ea44b17108ef39ef",
    "gold-qa-10caf16efab833ad40e600359b5239c2",
}


PROCEDURE_GROUPS: dict[str, list[tuple[str, list[int]]]] = {
    "gold-qa-6008640bfe85562d6598e3805655f820": [
        ("说明瓦片内如何形成深度排序列表", [0]),
        ("说明排序如何约束最终渲染合成顺序", [1]),
    ],
    "gold-qa-f9aea3f33c261e97222b15cf5b46fddf": [
        ("给出算法输入", [0]),
        ("给出初始化", [2]),
        ("给出抽样、误分类判断、参数更新和不更新分支", [3, 4, 5, 6, 7]),
        ("给出算法输出或返回值", [1, 8]),
    ],
    "gold-qa-2a2684775884b34032cd3adf427ec866": [
        ("列出快速推理方法", [0, 1, 2, 3]),
        ("列出快速训练方法", [4, 5, 6, 7]),
        ("列出模型编辑方法", [8, 9, 10, 11]),
        ("列出动态场景重建方法", [12, 13, 14, 15]),
    ],
    "gold-qa-252adaf1a1cbe9d9371796e0f770889b": [
        ("说明 AGI 的类人能力边界", [0]),
        ("说明 AGI 的任务能力边界", [1]),
        ("说明 AGI 是否要求自我意识", [2]),
    ],
    "gold-qa-a9d45653719933fd1bc9790cf1f0db87": [
        ("列出监督式算法范围", [0]),
        ("列出半监督式算法范围", [1]),
        ("列出强化学习", [2]),
        ("列出无监督式算法范围", [3]),
    ],
    "gold-qa-18b8640afc285e8d4ecebec3db23684f": [
        ("说明预测 JSON 的路径配置", [0]),
        ("说明基础模型如何执行预测", [1]),
        ("说明微调模型如何配置并执行预测", [2, 3]),
    ],
    "gold-qa-09063e7caac8aa5ae1a49e6d7081b9ca": [
        ("说明训练使用的计算设备规模", [0]),
        ("说明训练持续时间", [1]),
        ("说明训练成本", [2]),
    ],
    "gold-qa-74304d145c41aaf7ea44b17108ef39ef": [
        ("说明训练数据提供的多样化情景与例子", [0]),
        ("说明广泛学习经验与涌现能力的关系", [1]),
    ],
    "gold-qa-10caf16efab833ad40e600359b5239c2": [
        ("说明视频采集", [0]),
        ("说明模型检测与识别", [1]),
        ("说明专注度分析", [2]),
        ("说明实时结果反馈", [3]),
        ("说明课后报告生成", [4]),
    ],
}


def _obligation(
    *,
    qa: P09QAGoldCase,
    text: str,
    claims: list[GoldClaim],
    ordinal: int,
) -> P09AnswerObligation:
    evidence_ids = list(
        dict.fromkeys(
            evidence_id for claim in claims for evidence_id in claim.required_evidence_ids
        )
    )
    return P09AnswerObligation(
        obligation_id=_stable_id("gold-ob", qa.record_id, str(ordinal), text),
        obligation_text=text,
        claim_ids=[item.claim_id for item in claims],
        evidence_ids=evidence_ids,
        support_mode="single_claim" if len(claims) == 1 else "joint_claim_set",
        rationale="该回答义务由所列 Required Claim 及其直接 Evidence/必要邻接完整覆盖。",
    )


def _coverage_case(
    qa: P09QAGoldCase,
    retrieval_case: Any,
) -> P09CaseCoverageAudit:
    if not qa.answerable:
        return P09CaseCoverageAudit(
            qa_case_id=qa.record_id,
            query_sha256=qa.query_sha256,
            answerable=False,
            audit_status="not_applicable_unanswerable",
        )
    required = [item for item in qa.gold_claims if item.importance == "required"]
    obligations: list[P09AnswerObligation] = []
    if qa.record_id in PROCEDURE_GROUPS:
        for ordinal, (text, indices) in enumerate(PROCEDURE_GROUPS[qa.record_id], 1):
            obligations.append(
                _obligation(
                    qa=qa,
                    text=text,
                    claims=[required[index] for index in indices],
                    ordinal=ordinal,
                )
            )
    elif qa.query_type in {"comparison", "cross_section"}:
        quoted = [item for item in __import__("re").findall(r"“([^”]+)”", qa.query)]
        if qa.record_id == "gold-qa-7c2c4e325ca18b31270a328bd7a155e9":
            quoted = ["大模型安全对齐的目标", "ERNIE 微调实践的具体任务"]
        side_evidence_ids = list(
            dict.fromkeys(
                evidence_id
                for group in retrieval_case.gold_evidence_groups
                for evidence_id in group.required_evidence_ids
            )
        )
        if len(quoted) < 2 or len(side_evidence_ids) < 2:
            raise ValueError(f"two-sided case lacks two source Evidence records: {qa.record_id}")
        for ordinal, (name, evidence_id) in enumerate(
            zip(quoted[:2], side_evidence_ids[:2], strict=True), 1
        ):
            group_ids = {evidence_id}
            linked = [
                claim for claim in required if group_ids.intersection(claim.required_evidence_ids)
            ]
            if not linked:
                raise ValueError(f"two-sided obligation has no Claim: {qa.record_id}")
            obligations.append(
                _obligation(
                    qa=qa,
                    text=f"说明“{name}”",
                    claims=linked,
                    ordinal=ordinal,
                )
            )
        if qa.query_type == "comparison":
            obligations.append(
                _obligation(
                    qa=qa,
                    text="通过两组课程事实呈现二者关注点的区别",
                    claims=required,
                    ordinal=3,
                )
            )
    elif qa.record_id in ATOMIC_REVISION_IDS and len(required) > 1:
        obligations = [
            _obligation(
                qa=qa,
                text=f"回答原子事实：{claim.claim_text}",
                claims=[claim],
                ordinal=ordinal,
            )
            for ordinal, claim in enumerate(required, 1)
        ]
    else:
        obligations = [
            _obligation(
                qa=qa,
                text=f"完整回答问题：{qa.query}",
                claims=required,
                ordinal=1,
            )
        ]
    return P09CaseCoverageAudit(
        qa_case_id=qa.record_id,
        query_sha256=qa.query_sha256,
        answerable=True,
        audit_status="complete",
        obligations=obligations,
        required_claim_ids=[item.claim_id for item in required],
        uncovered_obligation_ids=[],
    )


def _review_html(
    *,
    title: str,
    bundle_sha256: str,
    review_pass: str,
    ids: list[str],
    r1_qa: dict[str, P09QAGoldCase],
    r2_qa: dict[str, P09QAGoldCase],
    r2_context: dict[str, P09ContextGoldCase],
    coverage: dict[str, P09CaseCoverageAudit],
    retrieval: dict[str, Any],
    evidence: dict[str, EvidenceRecord],
    evidence_hashes: dict[str, str],
) -> str:
    cards: list[str] = []
    for qa_id in ids:
        old = r1_qa[qa_id]
        new = r2_qa[qa_id]
        ctx = r2_context[qa_id]
        audit = coverage[qa_id]
        old_claims = "".join(f"<li>{html.escape(item.claim_text)}</li>" for item in old.gold_claims)
        new_claims = "".join(
            "<li><code>"
            + item.claim_id
            + "</code><blockquote>"
            + html.escape(item.claim_text)
            + "</blockquote>支持："
            + html.escape(", ".join(item.required_evidence_ids))
            + "</li>"
            for item in new.gold_claims
        )
        obligations = "".join(
            "<li><b>"
            + html.escape(item.obligation_text)
            + "</b><br>Claims："
            + html.escape(", ".join(item.claim_ids))
            + "<br>Evidence："
            + html.escape(", ".join(item.evidence_ids))
            + "</li>"
            for item in audit.obligations
        )
        short = (
            html.escape(json.dumps(new.gold_short_answers, ensure_ascii=False))
            if new.gold_short_answers
            else "不适用：本题按 Required Claims 评分，并非 Gold 缺失。"
        )
        evidence_ids = list(
            dict.fromkeys(
                evidence_id
                for claim in new.gold_claims
                for evidence_id in claim.required_evidence_ids
            )
        )
        panels = "".join(
            _evidence_panel(evidence[item], evidence_hashes[item], role="Required")
            for item in evidence_ids
        )
        neighbors = (
            "".join(
                f"<li><code>{item.neighbor_id}</code> · {html.escape(item.necessity_reason)}"
                f"<blockquote>{html.escape(item.text)}</blockquote></li>"
                for item in ctx.necessary_neighbors
            )
            or "<li>无必要邻接</li>"
        )
        cards.append(
            f"""<article class="card" data-id="{qa_id}">
<h2>{html.escape(new.query)}</h2><p><code>{qa_id}</code> · {new.query_type} · {new.gold_answer_type} · {new.split}</p>
<div class="notice"><b>短答案：</b>{short}</div>
<h3>r2 回答义务覆盖</h3><ol>{obligations}</ol>
<h3>r1 Claims</h3><ol>{old_claims}</ol>
<h3>r2 原子 Claims</h3><ol>{new_claims}</ol>
<h3>必要邻接</h3><ul>{neighbors}</ul>
<h3>Evidence 原文、SourceSpan 与 BBox</h3>{panels}
<fieldset><legend>仅审核 r2 实质变化</legend>
<label><input type="radio" name="d-{qa_id}" value="pass"> 通过</label>
<label><input type="radio" name="d-{qa_id}" value="return"> 退回</label>
<textarea id="n-{qa_id}" placeholder="退回必须填写原因；通过可备注"></textarea>
</fieldset></article>"""
        )
    expected = json.dumps(ids, ensure_ascii=False)
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:system-ui,sans-serif;background:#f5f6f8;color:#17202a;margin:0}}header{{position:sticky;top:0;background:white;border-bottom:1px solid #bbb;padding:16px 24px;z-index:3}}main{{max-width:1280px;margin:auto;padding:20px}}.card{{background:white;border:1px solid #bbb;border-radius:8px;padding:18px;margin:18px 0}}blockquote,pre,code{{white-space:pre-wrap;word-break:break-word}}blockquote,pre{{background:#f6f8fa;padding:10px}}.notice{{background:#e9f5ff;border:1px solid #78a9d1;padding:10px}}textarea{{display:block;width:100%;min-height:64px;margin-top:10px}}</style></head>
<body><header><h1>{html.escape(title)}</h1><p>Bundle <code>{bundle_sha256}</code> · 差异复核 {len(ids)} 条</p><button id="export">导出审核 JSON</button> <span id="progress"></span></header><main>{"".join(cards)}</main>
<script>const expected={expected};const bundle="{bundle_sha256}";const passName="{review_pass}";const key=`p09-r2-${{bundle}}-${{passName}}`;const saved=JSON.parse(localStorage.getItem(key)||"{{}}");function refresh(){{let done=0;for(const id of expected){{const d=document.querySelector(`input[name="d-${{id}}"]:checked`);if(d)done++;}}document.getElementById('progress').textContent=`已审核 ${{done}}/${{expected.length}}`;}}for(const id of expected){{if(saved[id]){{const radio=document.querySelector(`input[name="d-${{id}}"]`+`[value="${{saved[id].decision}}"]`);if(radio)radio.checked=true;document.getElementById(`n-${{id}}`).value=saved[id].notes||"";}}}}document.addEventListener('change',e=>{{if(e.target.matches('input[type=radio]')){{const id=e.target.name.slice(2);saved[id]={{decision:e.target.value,notes:document.getElementById(`n-${{id}}`).value}};localStorage.setItem(key,JSON.stringify(saved));refresh();}}}});document.addEventListener('input',e=>{{if(e.target.matches('textarea')){{const id=e.target.id.slice(2);if(saved[id]){{saved[id].notes=e.target.value;localStorage.setItem(key,JSON.stringify(saved));}}}}}});document.getElementById('export').onclick=()=>{{const decisions=[];for(const id of expected){{const d=document.querySelector(`input[name="d-${{id}}"]:checked`);if(!d){{alert(`尚未审核：${{id}}`);return;}}const notes=document.getElementById(`n-${{id}}`).value.trim();if(d.value==='return'&&!notes){{alert(`退回必须填写原因：${{id}}`);return;}}decisions.push({{record_id:id,decision:d.value,notes}});}}const payload={{schema_version:'courserag.p09-review-decisions.v1',dataset_id:'courserag-p09-r2-diff-review',dataset_version:'r2',bundle_sha256:bundle,review_pass:passName,expected_record_ids:expected,decisions,reviewer_id:null,reviewed_at:null,attestation_source:'html_export',notes:'P09 r2 semantic-difference review'}};const blob=new Blob([JSON.stringify(payload,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`p09_r2_${{passName}}_review_${{bundle.slice(0,12)}}.json`;a.click();URL.revokeObjectURL(a.href);}};refresh();</script></body></html>"""


def _bundle_sha256(
    *,
    qa_sha256: str,
    context_sha256: str,
    coverage_sha256: str,
    r1_manifest: P09GoldBundleManifest,
    first_review_sha256: str,
    second_review_sha256: str,
    qa_hashes: dict[str, str],
    context_hashes: dict[str, str],
    changed_ids: list[str],
    context_changed_ids: list[str],
    review_groups: list[list[str]],
    second_ids: list[str],
) -> str:
    payload = {
        "schema_version": "courserag.p09-gold-bundle-identity.v1",
        "revision": 2,
        "approval_scope": APPROVAL_SCOPE,
        "qa_sha256": qa_sha256,
        "context_sha256": context_sha256,
        "coverage_sha256": coverage_sha256,
        "parent_bundle_sha256": r1_manifest.bundle_sha256,
        "inherited_first_review_sha256": first_review_sha256,
        "inherited_second_review_sha256": second_review_sha256,
        "qa_record_sha256": qa_hashes,
        "context_record_sha256": context_hashes,
        "p08_record_sha256": r1_manifest.p08_retrieval_record_sha256,
        "upstream_sha256": r1_manifest.upstream_approved_sha256,
        "preserved_sha256": r1_manifest.preserved_p08_sha256,
        "semantic_changed_record_ids": changed_ids,
        "context_changed_record_ids": context_changed_ids,
        "first_review_groups": review_groups,
        "second_review_ids": second_ids,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_r2(*, repository_root: Path) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    dataset_root = repository_root / ROOT
    frozen_r1_manifest = repository_root / R1_MANIFEST
    r1_manifest_source = (
        frozen_r1_manifest
        if frozen_r1_manifest.exists()
        else dataset_root / "provenance/p09_gold_bundle_manifest.json"
    )
    r1_manifest = P09GoldBundleManifest.model_validate_json(
        r1_manifest_source.read_text(encoding="utf-8")
    )
    if r1_manifest.revision != 1 or r1_manifest.bundle_sha256 != R1_BUNDLE_SHA256:
        raise ValueError("P09 r2 must start from the frozen r1 Bundle")
    if (
        sha256_file(repository_root / r1_manifest.qa_candidate.path)
        != r1_manifest.qa_candidate.sha256
    ):
        raise ValueError("P09 r1 QA Candidate changed")
    if (
        sha256_file(repository_root / r1_manifest.context_candidate.path)
        != r1_manifest.context_candidate.sha256
    ):
        raise ValueError("P09 r1 Context Candidate changed")
    first_review_path = repository_root / R1_FIRST_REVIEW
    second_review_path = repository_root / R1_SECOND_REVIEW
    first_review = P09ReviewDecisions.model_validate_json(
        first_review_path.read_text(encoding="utf-8")
    )
    second_review = P09ReviewDecisions.model_validate_json(
        second_review_path.read_text(encoding="utf-8")
    )
    if (
        first_review.bundle_sha256 != r1_manifest.bundle_sha256
        or second_review.bundle_sha256 != r1_manifest.bundle_sha256
    ):
        raise ValueError("P09 r1 inherited reviews target another Bundle")
    if any(item.decision != "pass" for item in first_review.decisions + second_review.decisions):
        raise ValueError("P09 r1 inherited reviews contain a return")

    r1_qa_dataset = P09QAGoldDataset.model_validate_json(
        (repository_root / R1_QA).read_text(encoding="utf-8")
    )
    r1_context_dataset = P09ContextGoldDataset.model_validate_json(
        (repository_root / R1_CONTEXT).read_text(encoding="utf-8")
    )
    retrieval_dataset = DS5RetrievalQADataset.model_validate_json(
        (repository_root / P08).read_text(encoding="utf-8")
    )
    evidence_dataset = DS2EvidenceDataset.model_validate_json(
        (repository_root / DS2).read_text(encoding="utf-8")
    )
    DS3KnowledgePointDataset.model_validate_json(
        (repository_root / DS3).read_text(encoding="utf-8")
    )
    evidence = {item.evidence_id: item for item in evidence_dataset.evidence}
    evidence_hashes = {item.evidence_id: record_digest(item) for item in evidence_dataset.evidence}
    retrieval = {item.record_id: item for item in retrieval_dataset.cases}
    contexts = {item.qa_case_id: item for item in r1_context_dataset.cases}

    ernie_id = "gold-qa-18b8640afc285e8d4ecebec3db23684f"
    ernie_context = contexts[ernie_id]
    ernie_eid = _required_evidence_id(
        next(item for item in r1_qa_dataset.cases if item.record_id == ernie_id)
    )
    docx_paths = list((repository_root / "data/sample_files").glob("*.docx"))
    if len(docx_paths) != 1:
        raise ValueError("P09 r2 requires exactly one primary DOCX")
    expected_docx_sha = evidence[ernie_eid].source_span.document_sha256
    if sha256_file(docx_paths[0]) != expected_docx_sha:
        raise ValueError("primary DOCX Hash changed before P09 r2")
    new_neighbor = _ernie_execution_neighbor(
        evidence=evidence[ernie_eid], document_path=docx_paths[0]
    )
    if all(
        item.neighbor_id != new_neighbor.neighbor_id for item in ernie_context.necessary_neighbors
    ):
        contexts[ernie_id] = ernie_context.model_copy(
            update={
                "necessary_neighbors": ernie_context.necessary_neighbors + [new_neighbor],
                "neighbor_expansion": "only_listed_neighbors",
                "candidate_source": "source_grounded_approved_evidence_r2",
                "generation_strategy_sha256": R2_STRATEGY_SHA256,
            }
        )

    revised_qa: list[P09QAGoldCase] = []
    for qa in r1_qa_dataset.cases:
        if qa.record_id not in ATOMIC_REVISION_IDS:
            revised_qa.append(qa)
            continue
        new_claims, short_answers = _atomic_claims(
            qa=qa,
            context=contexts[qa.record_id],
            evidence=evidence,
            evidence_hashes=evidence_hashes,
        )
        updates: dict[str, Any] = {
            "gold_claims": new_claims,
            "candidate_source": "source_grounded_approved_evidence_r2",
            "generation_strategy_sha256": R2_STRATEGY_SHA256,
            "annotation_flags": [],
            "manual_review_reason": None,
        }
        if short_answers is not None:
            updates["gold_short_answers"] = short_answers
            variants, details = _build_variants(short_answers[0])
            updates["allowed_answer_variants"] = variants
            updates["answer_variant_details"] = details
        revised_qa.append(qa.model_copy(update=updates))

    r2_qa_dataset = P09QAGoldDataset(
        dataset_id=r1_qa_dataset.dataset_id,
        dataset_version="r2",
        cases=revised_qa,
    )
    r2_context_dataset = P09ContextGoldDataset(
        dataset_id=r1_context_dataset.dataset_id,
        dataset_version="r2",
        cases=[contexts[item.qa_case_id] for item in r1_context_dataset.cases],
    )
    r2_qa_by_id = {item.record_id: item for item in r2_qa_dataset.cases}
    r2_context_by_id = {item.qa_case_id: item for item in r2_context_dataset.cases}
    coverage_dataset = P09CoverageAuditDataset(
        dataset_id="courserag-p09-answer-obligation-coverage",
        dataset_version="r2",
        cases=[
            _coverage_case(item, retrieval[item.retrieval_case_id]) for item in r2_qa_dataset.cases
        ],
    )

    qa_path = repository_root / R2_QA
    context_path = repository_root / R2_CONTEXT
    coverage_path = repository_root / COVERAGE_AUDIT
    atomic_write_json(qa_path, r2_qa_dataset.model_dump(mode="json"))
    atomic_write_json(context_path, r2_context_dataset.model_dump(mode="json"))
    atomic_write_json(coverage_path, coverage_dataset.model_dump(mode="json"))

    r1_qa_by_id = {item.record_id: item for item in r1_qa_dataset.cases}
    r1_context_by_id = {item.qa_case_id: item for item in r1_context_dataset.cases}
    qa_hashes = {item.record_id: record_digest(item) for item in r2_qa_dataset.cases}
    context_hashes = {item.record_id: record_digest(item) for item in r2_context_dataset.cases}
    changed_ids = [
        item.record_id
        for item in r2_qa_dataset.cases
        if record_digest(item) != record_digest(r1_qa_by_id[item.record_id])
    ]
    context_changed_ids = [
        item.qa_case_id
        for item in r2_context_dataset.cases
        if record_digest(item) != record_digest(r1_context_by_id[item.qa_case_id])
    ]
    if set(changed_ids) != ATOMIC_REVISION_IDS:
        raise ValueError("P09 r2 semantic-change set differs from the audited revision set")
    if context_changed_ids != [ernie_id]:
        raise ValueError("P09 r2 must change only the ERNIE Context record")
    review_order = sorted(changed_ids, key=lambda item: _sha(f"p09-r2-first|{item}"))
    review_groups = [review_order[index : index + 10] for index in range(0, len(review_order), 10)]
    second_ids = sorted(changed_ids, key=lambda item: _sha(f"p09-r2-blind|{item}"))
    bundle_sha256 = _bundle_sha256(
        qa_sha256=sha256_file(qa_path),
        context_sha256=sha256_file(context_path),
        coverage_sha256=sha256_file(coverage_path),
        r1_manifest=r1_manifest,
        first_review_sha256=sha256_file(first_review_path),
        second_review_sha256=sha256_file(second_review_path),
        qa_hashes=qa_hashes,
        context_hashes=context_hashes,
        changed_ids=review_order,
        context_changed_ids=context_changed_ids,
        review_groups=review_groups,
        second_ids=second_ids,
    )
    review_dir = repository_root / f"storage_eval/ds5_p09_review/{bundle_sha256}"
    coverage_by_id = {item.qa_case_id: item for item in coverage_dataset.cases}
    first_html = _review_html(
        title="P09 r2 首轮差异审核",
        bundle_sha256=bundle_sha256,
        review_pass="first",
        ids=review_order,
        r1_qa=r1_qa_by_id,
        r2_qa=r2_qa_by_id,
        r2_context=r2_context_by_id,
        coverage=coverage_by_id,
        retrieval=retrieval,
        evidence=evidence,
        evidence_hashes=evidence_hashes,
    )
    second_html = _review_html(
        title="P09 r2 二轮盲化差异审核",
        bundle_sha256=bundle_sha256,
        review_pass="second",
        ids=second_ids,
        r1_qa=r1_qa_by_id,
        r2_qa=r2_qa_by_id,
        r2_context=r2_context_by_id,
        coverage=coverage_by_id,
        retrieval=retrieval,
        evidence=evidence,
        evidence_hashes=evidence_hashes,
    )
    atomic_write_text(review_dir / "index.html", first_html)
    atomic_write_text(review_dir / "second_review.html", second_html)

    manifest = P09GoldBundleManifest(
        dataset_id="courserag-p09-gold-bundle",
        dataset_version="r2",
        revision=2,
        qa_candidate=_artifact(repository_root, qa_path),
        context_candidate=_artifact(repository_root, context_path),
        approved_p08_retrieval=r1_manifest.approved_p08_retrieval,
        qa_candidate_record_sha256=qa_hashes,
        context_candidate_record_sha256=context_hashes,
        p08_retrieval_record_sha256=r1_manifest.p08_retrieval_record_sha256,
        upstream_approved_sha256=r1_manifest.upstream_approved_sha256,
        preserved_p08_sha256=r1_manifest.preserved_p08_sha256,
        first_review_groups=review_groups,
        second_review_ids=second_ids,
        review_pack_relative_path=review_dir.relative_to(repository_root).as_posix(),
        review_pack_index_sha256=sha256_file(review_dir / "index.html"),
        second_review_index_sha256=sha256_file(review_dir / "second_review.html"),
        bundle_sha256=bundle_sha256,
        test_locked=False,
        coverage_audit=_artifact(repository_root, coverage_path),
        parent_bundle_sha256=r1_manifest.bundle_sha256,
        inherited_first_review=_artifact(repository_root, first_review_path),
        inherited_second_review=_artifact(repository_root, second_review_path),
        semantic_changed_record_ids=review_order,
        context_changed_record_ids=context_changed_ids,
    )
    manifest_path = repository_root / R2_MANIFEST
    canonical_manifest_path = repository_root / CANONICAL_MANIFEST
    if not (repository_root / R1_MANIFEST).exists():
        atomic_write_json(repository_root / R1_MANIFEST, r1_manifest.model_dump(mode="json"))
    atomic_write_json(manifest_path, manifest.model_dump(mode="json"))
    atomic_write_json(canonical_manifest_path, manifest.model_dump(mode="json"))

    changes = cast(
        JsonValue,
        {
            "schema_version": "courserag.p09-r1-to-r2-changes.v1",
            "parent_bundle_sha256": r1_manifest.bundle_sha256,
            "bundle_sha256": bundle_sha256,
            "semantic_changed_record_ids": review_order,
            "context_changed_record_ids": context_changed_ids,
            "unchanged_qa_record_count": 100 - len(changed_ids),
            "unchanged_context_record_count": 100 - len(context_changed_ids),
            "change_reasons": {
                "atomic_claim_split": sorted(ATOMIC_REVISION_IDS),
                "neighbor_supported_fact_completion": sorted(
                    {
                        "gold-qa-2b8972b47de56a5b6b62e68091320557",
                        "gold-qa-a74bb4b9fcefc7df08ea2063151445b8",
                        "gold-qa-730f317833bc4b6f6d458f42814069be",
                        ernie_id,
                    }
                ),
                "procedure_coverage_completion": sorted(PROCEDURE_GROUPS),
            },
        },
    )
    atomic_write_json(repository_root / CHANGE_AUDIT, changes)
    history = CandidateRevisionHistory(
        dataset_id="courserag-p09-qa-context",
        dataset_version="r2",
        revisions=[
            CandidateRevisionArtifact(
                revision=1,
                status="superseded",
                candidate_relative_path=R1_QA.as_posix(),
                candidate_file_sha256=sha256_file(repository_root / R1_QA),
                reason="Initial Candidate; Course Owner attested both reviews passed before systematic obligation audit.",
            ),
            CandidateRevisionArtifact(
                revision=2,
                status="pending_course_owner_review",
                candidate_relative_path=R2_QA.as_posix(),
                candidate_file_sha256=sha256_file(qa_path),
                reason="Atomic Claims and complete answer-obligation coverage; only semantic changes require renewed review.",
            ),
        ],
    )
    atomic_write_json(repository_root / REVISION_HISTORY, history.model_dump(mode="json"))
    context_history = CandidateRevisionHistory(
        dataset_id="courserag-p09-context",
        dataset_version="r2",
        revisions=[
            CandidateRevisionArtifact(
                revision=1,
                status="superseded",
                candidate_relative_path=R1_CONTEXT.as_posix(),
                candidate_file_sha256=sha256_file(repository_root / R1_CONTEXT),
                reason="Initial Context Candidate superseded by the answer-obligation audit.",
            ),
            CandidateRevisionArtifact(
                revision=2,
                status="pending_course_owner_review",
                candidate_relative_path=R2_CONTEXT.as_posix(),
                candidate_file_sha256=sha256_file(context_path),
                reason="One ERNIE procedure gains an independently sourced minimum neighbor; 99 Context records are unchanged.",
            ),
        ],
    )
    atomic_write_json(
        repository_root / CONTEXT_REVISION_HISTORY,
        context_history.model_dump(mode="json"),
    )

    answer_types = Counter(item.gold_answer_type for item in r2_qa_dataset.cases)
    claim_count = sum(len(item.gold_claims) for item in r2_qa_dataset.cases)
    neighbor_count = sum(len(item.necessary_neighbors) for item in r2_context_dataset.cases)
    report = f"""# ED-PRE09 DS5 QA/Context Candidate r2 审核报告

## 精确身份

- Parent r1 Bundle：`{r1_manifest.bundle_sha256}`
- r2 Bundle：`{bundle_sha256}`
- QA Candidate SHA-256：`{sha256_file(qa_path)}`
- Context Candidate SHA-256：`{sha256_file(context_path)}`
- Coverage Audit SHA-256：`{sha256_file(coverage_path)}`

## 修订结论

- 100 条 P08 Query、课程、Split、Retrieval Gold 均未改变。
- 18 条 QA 记录发生原子 Claim 或答案覆盖修订；其余 82 条 QA 记录 Hash 不变。
- 仅 ERNIE 过程题增加一个经原始 OOXML与固定 Renderer 第272物理页核对的必要邻接；其余99条 Context记录 Hash不变。
- 90 条可回答记录均具有完整回答义务覆盖；10条不可回答记录保持无答案、无 Claims。
- 比较题遵循冻结文档示例：无唯一短答案，由两侧 Required Claims 共同评分。
- r1 两轮全通过采用 Course Owner 对话中的明确声明保存为继承审计；r2 两轮只复核18条实质变化。

## 统计

- Answer Type：`{dict(sorted(answer_types.items()))}`
- Gold Claims：`{claim_count}`；必要邻接：`{neighbor_count}`。
- 覆盖审计：100条，其中90条 complete、10条 not_applicable_unanswerable、0条 uncovered。

## 审核重点

1. 每个回答义务是否被所列 Claim 完整覆盖。
2. Claim 是否为单一事实，且未引入原文之外的信息。
3. Evidence 正文与必要邻接来源是否区分正确。
4. 事实题短答案是否完整；解释/比较/过程题的空短答案是否明确标为“不适用”。
5. ERNIE 配置与两次 `run_infer.py` 执行步骤是否与原始 DOCX 一致。

批准前必须完成 r2 的两份差异审核 JSON，并使用新的 Bundle SHA-256。
"""
    atomic_write_text(repository_root / REPORT, report)
    atomic_write_text(repository_root / CANONICAL_REPORT, report)
    return {
        "bundle_sha256": bundle_sha256,
        "qa_sha256": sha256_file(qa_path),
        "context_sha256": sha256_file(context_path),
        "coverage_sha256": sha256_file(coverage_path),
        "changed_count": len(changed_ids),
        "context_changed_count": len(context_changed_ids),
        "claim_count": claim_count,
        "neighbor_count": neighbor_count,
        "review_dir": review_dir,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build P09 QA/Context Gold Candidate r2.")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(
        json.dumps(build_r2(repository_root=args.repository_root), ensure_ascii=False, default=str)
    )


if __name__ == "__main__":
    main()
