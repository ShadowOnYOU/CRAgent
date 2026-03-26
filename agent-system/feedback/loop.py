"""
反馈循环
实现三态反馈和数据收集
"""
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

import sys
sys.path.insert(0, '.')

from models import ReviewResult, ReviewIssue, FeedbackStatus


class FeedbackLoop:
    """反馈循环管理器"""
    
    def __init__(self, data_dir: str = "./data/feedback"):
        """
        初始化反馈循环
        
        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
        # 反馈统计
        self.stats = {
            "accept": 0,
            "ignore": 0,
            "reject": 0
        }
    
    def record_feedback(self, pr_id: str, issue_index: int, 
                        status: FeedbackStatus, 
                        user_comment: str = "") -> bool:
        """
        记录用户反馈
        
        Args:
            pr_id: PR ID
            issue_index: 问题索引
            status: 反馈状态
            user_comment: 用户备注
            
        Returns:
            是否成功记录
        """
        record = {
            "pr_id": pr_id,
            "issue_index": issue_index,
            "status": status.value,
            "user_comment": user_comment,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # 追加到反馈文件
            feedback_file = os.path.join(self.data_dir, "feedback.jsonl")
            with open(feedback_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
            
            # 更新统计
            self.stats[status.value] += 1
            
            return True
        except Exception as e:
            print(f"记录反馈失败：{e}")
            return False
    
    def accept(self, pr_id: str, issue_index: int, comment: str = "") -> bool:
        """标记为接受"""
        return self.record_feedback(pr_id, issue_index, FeedbackStatus.ACCEPT, comment)
    
    def ignore(self, pr_id: str, issue_index: int, comment: str = "") -> bool:
        """标记为忽略"""
        return self.record_feedback(pr_id, issue_index, FeedbackStatus.IGNORE, comment)
    
    def reject(self, pr_id: str, issue_index: int, comment: str = "") -> bool:
        """标记为拒绝（误报）"""
        return self.record_feedback(pr_id, issue_index, FeedbackStatus.REJECT, comment)
    
    def get_feedback_history(self, pr_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取反馈历史
        
        Args:
            pr_id: 可选的 PR ID 过滤
            
        Returns:
            反馈记录列表
        """
        feedback_file = os.path.join(self.data_dir, "feedback.jsonl")
        
        if not os.path.exists(feedback_file):
            return []
        
        records = []
        try:
            with open(feedback_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        record = json.loads(line)
                        if pr_id is None or record.get("pr_id") == pr_id:
                            records.append(record)
        except Exception:
            pass
        
        return records
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        # 从文件重新计算
        records = self.get_feedback_history()
        
        stats = {"accept": 0, "ignore": 0, "reject": 0}
        for record in records:
            status = record.get("status", "ignore")
            if status in stats:
                stats[status] += 1
        
        return stats
    
    def get_acceptance_rate(self) -> float:
        """获取采纳率"""
        stats = self.get_stats()
        total = sum(stats.values())
        
        if total == 0:
            return 0.0
        
        return stats["accept"] / total
    
    def export_dataset(self, output_path: str) -> bool:
        """
        导出评测数据集
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            是否成功导出
        """
        records = self.get_feedback_history()
        
        if not records:
            return False
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False
    
    def analyze_bad_cases(self) -> List[Dict[str, Any]]:
        """
        分析误报案例
        
        Returns:
            误报案例列表
        """
        records = self.get_feedback_history()
        
        bad_cases = []
        for record in records:
            if record.get("status") == "reject":
                bad_cases.append({
                    "pr_id": record.get("pr_id"),
                    "issue_index": record.get("issue_index"),
                    "user_comment": record.get("user_comment"),
                    "timestamp": record.get("timestamp")
                })
        
        return bad_cases
    
    def save_review_result(self, result: ReviewResult) -> bool:
        """
        保存评审结果用于后续分析
        
        Args:
            result: 评审结果
            
        Returns:
            是否成功保存
        """
        try:
            result_file = os.path.join(self.data_dir, f"result_{result.pr_id}.json")
            
            data = {
                "pr_id": result.pr_id,
                "summary": result.summary,
                "issues": [
                    {
                        "issue_type": i.issue_type,
                        "severity": i.severity.value,
                        "message": i.message,
                        "file_path": i.file_path,
                        "line_number": i.line_number,
                        "evidence": i.evidence,
                        "suggestion": i.suggestion,
                        "confidence": i.confidence
                    }
                    for i in result.issues
                ],
                "reasoning_trace": result.reasoning_trace,
                "timestamp": datetime.now().isoformat()
            }
            
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"保存评审结果失败：{e}")
            return False
    
    def load_review_result(self, pr_id: str) -> Optional[Dict[str, Any]]:
        """
        加载保存的评审结果
        
        Args:
            pr_id: PR ID
            
        Returns:
            评审结果数据
        """
        result_file = os.path.join(self.data_dir, f"result_{pr_id}.json")
        
        if not os.path.exists(result_file):
            return None
        
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None