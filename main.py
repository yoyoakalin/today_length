import asyncio
import random
import aiosqlite
import os
from datetime import datetime
from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.model import MessageChain

@register("daily_length_db", "GeMio", "支持艾特与SQL存储的长度插件", "1.2.1")
class DailyLengthPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.db_path = os.path.join(os.path.dirname(__file__), "data.db")

    async def _init_db(self):
        """初始化数据库表"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS records (
                    user_id TEXT PRIMARY KEY,
                    nickname TEXT,
                    length REAL,
                    record_date TEXT
                )
            ''')
            await db.commit()

    async def _get_user_nickname(self, event: AstrMessageEvent, user_id: str) -> str:
        """获取用户昵称"""
        name = event.get_sender_name()
        return name if name else f"用户_{user_id[-4:]}"

    @filter.command("今日长度")
    async def handle_length(self, event: AstrMessageEvent):
        await self._init_db()
        user_id = str(event.get_sender_id())
        today = datetime.now().strftime("%Y-%m-%d")

        async with aiosqlite.connect(self.db_path) as db:
            # 1. 查询今日记录
            async with db.execute(
                "SELECT length, nickname FROM records WHERE user_id = ? AND record_date = ?", 
                (user_id, today)
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                length, nickname = row
                is_new = False
            else:
                # 2. 生成新记录（保留两位小数，符合 README 描述）
                length = round(random.uniform(1, 30), 2)
                nickname = await self._get_user_nickname(event, user_id)
                is_new = True

                await db.execute(
                    "REPLACE INTO records (user_id, nickname, length, record_date) VALUES (?, ?, ?, ?)",
                    (user_id, nickname, length, today)
                )
                await db.commit()

        # 3. 构造带艾特的消息链
        chain = MessageChain()
        chain.at(user_id) # 添加艾特
        
        msg_text = f" {nickname} 今天的长度是 {length}cm！"
        if not is_new:
            msg_text = "（今日已锁定）" + msg_text
            
        chain.text(msg_text)
        yield event.chain_result(chain)

    @filter.command("长度排行")
    async def handle_rank(self, event: AstrMessageEvent):
        await self._init_db()
        today = datetime.now().strftime("%Y-%m-%d")

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT nickname, length FROM records WHERE record_date = ? ORDER BY length DESC", 
                (today,)
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            yield event.plain_result("今天还没有人参与测试哦~")
            return

        chunk_size = 15
        header = "🏆 今日长度排行榜 🏆\n" + "—" * 20 + "\n"
        
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            rank_text = header if i == 0 else ""
            for index, (nick, l_val) in enumerate(chunk, start=i + 1):
                # 排行榜就不一一艾特了，否则会造成大规模打扰，仅显示昵称
                rank_text += f"{index}. {nick}: {l_val:.2f}cm\n"
            
            yield event.plain_result(rank_text.strip())