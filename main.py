import random
import json
import logging
from datetime import datetime
from pathlib import Path

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register, StarTools
import astrbot.api.message_components as Comp

logger = logging.getLogger("astrbot")

@register("today_length", "GeMio", "全员排行榜版：今日长度", "1.4.0")
class TodayLengthPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir("today_length")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path = self.data_dir / "records.json"
        self.storage = self._load_data()

    def _load_data(self) -> dict:
        if not self.storage_path.exists():
            return {"date": "", "records": {}}
        try:
            return json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            return {"date": "", "records": {}}

    def _save_data(self):
        self.storage_path.write_text(json.dumps(self.storage, ensure_ascii=False, indent=4), encoding="utf-8")

    def _check_date(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        if self.storage.get("date") != today_str:
            self.storage = {"date": today_str, "records": {}}
            self._save_data()
        return today_str

    @filter.command("今日长度")
    async def handle_length(self, event: AstrMessageEvent):
        today_str = self._check_date()
        user_id = event.get_sender_id()
        user_records = self.storage["records"]
        
        if user_id in user_records:
            length = user_records[user_id]
            is_new = False
        else:
            length = round(random.uniform(1, 20), 2)
            user_records[user_id] = length
            self._save_data()
            is_new = True

        msg = f"你的今日长度为：{length} cm"
        if not is_new: msg = "（已锁定）" + msg
        
        yield event.chain_result([Comp.At(qq=user_id), Comp.Plain(f" {msg}")])

    @filter.command("长度排行", alias={"全员榜", "所有人长度"})
    async def handle_rank(self, event: AstrMessageEvent):
        """生成全员排行榜"""
        self._check_date()
        user_records = self.storage.get("records", {})

        if not user_records:
            yield event.plain_result("今日榜单空空如也，快来发送“今日长度”抢占沙发！")
            return

        # 排序：从大到小
        sorted_ranks = sorted(user_records.items(), key=lambda x: x[1], reverse=True)
        total_count = len(sorted_ranks)
        
        # 构造标题
        rank_text = f"📊 今日全员长度榜 ({self.storage['date']})\n"
        rank_text += f"当前共 {total_count} 位猛男参与测试\n"
        rank_text += "━━━━━━━━━━━━━━\n"
        
        # 遍历所有人
        for i, (uid, length) in enumerate(sorted_ranks, 1):
            # 前三名使用特殊勋章
            if i == 1: medal = "🥇 "
            elif i == 2: medal = "🥈 "
            elif i == 3: medal = "🥉 "
            else: medal = f"[{i}] "
            
            # 格式：[排名] QQ号 —— 长度cm
            rank_text += f"{medal}{uid}：{length} cm\n"
            
            # 每 30 人插入一个分隔符，防止视觉疲劳（可选）
            if i % 30 == 0 and i != total_count:
                rank_text += "┈┈┈┈┈┈┈┈┈┈┈┈\n"

        rank_text += "━━━━━━━━━━━━━━\n"
        rank_text += "提示：长度纯属随机，切勿当真。"

        yield event.plain_result(rank_text)

    def terminate(self):
        logger.info("[TodayLength] 插件已安全卸载")