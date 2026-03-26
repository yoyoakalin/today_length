import random
import json
import asyncio
from datetime import datetime
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register, StarTools
import astrbot.api.message_components as Comp

@register("today_length", "GeMio", "全功能名片版：今日长度", "1.6.0")
class TodayLengthPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir("today_length")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path = self.data_dir / "records.json"
        self.lock = asyncio.Lock()
        self.storage = self._load_data()

    def _load_data(self) -> dict:
        default_data = {"date": "", "records": {}} # records 格式: {uid: {"len": 12, "name": "昵称"}}
        if not self.storage_path.exists():
            return default_data
        try:
            content = self.storage_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if "records" in data:
                data["records"] = {str(k): v for k, v in data["records"].items()}
            return data
        except Exception as e:
            logger.error(f"[TodayLength] 加载失败: {e}")
            return default_data

    async def _save_data(self):
        try:
            content = json.dumps(self.storage, ensure_ascii=False, indent=4)
            self.storage_path.write_text(content, encoding="utf-8")
        except Exception as e:
            logger.error(f"[TodayLength] 存储失败: {e}")

    async def _get_today_data(self) -> dict:
        async with self.lock:
            today_str = datetime.now().strftime("%Y-%m-%d")
            if self.storage.get("date") != today_str:
                self.storage = {"date": today_str, "records": {}}
                await self._save_data()
            return self.storage

    async def _get_user_nickname(self, event: AstrMessageEvent, user_id: int) -> str:
        """获取用户昵称/群名片的核心逻辑"""
        try:
            group_id = event.get_group_id()
            if group_id:
                # 调用底层 OneBot API 获取群成员信息
                payload = {"group_id": int(group_id), "user_id": int(user_id)}
                # 兼容不同版本的接口调用方式
                resp = await event.bot.get_group_member_info(**payload)
                if resp:
                    # 优先获取群名片，其次是昵称
                    return resp.get("card") or resp.get("nickname") or str(user_id)
            
            # 如果不是群聊或获取失败，尝试获取陌生人信息
            resp = await event.bot.get_stranger_info(user_id=int(user_id))
            return resp.get("nickname") or str(user_id)
        except Exception as e:
            logger.debug(f"[TodayLength] 获取昵称失败 {user_id}: {e}")
            return str(user_id)

    @filter.command("今日长度")
    async def handle_length(self, event: AstrMessageEvent):
        await self._get_today_data()
        user_id = str(event.get_sender_id())
        
        async with self.lock:
            user_records = self.storage["records"]
            if user_id in user_records:
                data = user_records[user_id]
                length = data["len"]
                nickname = data.get("name", user_id)
                is_new = False
            else:
                length = round(random.uniform(1, 20), 2)
                # 获取当前最新的昵称并存入缓存
                nickname = await self._get_user_nickname(event, int(user_id))
                user_records[user_id] = {"len": length, "name": nickname}
                await self._save_data()
                is_new = True

        msg = f"{nickname}，你的今日长度为：{length} cm"
        if not is_new: msg = "（今日已锁定）" + msg
        
        yield event.chain_result([Comp.At(qq=user_id), Comp.Plain(f" {msg}")])

    @filter.command("长度排行")
    async def handle_rank(self, event: AstrMessageEvent):
        await self._get_today_data()
        
        async with self.lock:
            user_records = self.storage.get("records", {})

        if not user_records:
            yield event.plain_result("今日榜单空空如也。")
            return

        # 排序：根据记录中的 'len' 字段排序
        sorted_ranks = sorted(
            user_records.items(), 
            key=lambda x: x[1]['len'], 
            reverse=True
        )
        
        header = f"📊 今日全员榜 ({self.storage['date']})\n━━━━━━━━━━━━━━\n"
        lines = []
        for i, (uid, data) in enumerate(sorted_ranks, 1):
            medal = "🥇 " if i == 1 else "🥈 " if i == 2 else "🥉 " if i == 3 else f"[{i}] "
            name = data.get("name", uid)
            length = data.get("len", 0)
            lines.append(f"{medal}{name}：{length} cm")

        # 分片发送，每 50 人一组
        chunk_size = 50 
        for i in range(0, len(lines), chunk_size):
            chunk = lines[i:i + chunk_size]
            output = header + "\n".join(chunk) if i == 0 else "\n".join(chunk)
            yield event.plain_result(output)

    def terminate(self):
        logger.info("[TodayLength] 插件安全卸载")