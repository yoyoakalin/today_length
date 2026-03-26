import asyncio
import random
import aiosqlite
import os
from datetime import datetime
from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

@register("daily_length_db", "GeMio", "SQL版异步长度插件", "1.2.0")
class DailyLengthPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.db_path = os.path.join(os.path.dirname(__file__), "data.db")
        self.lock = asyncio.Lock() # 用于内存级操作保护

    async def _init_db(self):
        """初始化数据库表"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS records (
                    user_id TEXT PRIMARY KEY,
                    nickname TEXT,
                    length INTEGER,
                    record_date TEXT
                )
            ''')
            await db.commit()

    async def _get_user_nickname(self, event: AstrMessageEvent, user_id: str) -> str:
        name = event.get_sender_name()
        return name if name else f"用户_{user_id[-4:]}"

    @filter.command("今日长度")
    async def handle_length(self, event: AstrMessageEvent):
        await self._init_db() # 确保表已创建
        user_id = str(event.get_sender_id())
        today = datetime.now().strftime("%Y-%m-%d")

        async with aiosqlite.connect(self.db_path) as db:
            # 1. 检查今日是否已有记录
            async with db.execute(
                "SELECT length, nickname FROM records WHERE user_id = ? AND record_date = ?", 
                (user_id, today)
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                length, nickname = row
                is_new = False
            else:
                # 2. 准备新数据（锁外获取昵称，提升并发）
                length = random.randint(1, 30)
                nickname = await self._get_user_nickname(event, user_id)
                is_new = True

                # 3. 写入/更新数据
                # 注意：这里使用 REPLACE 或先删除旧日期数据，保证一人一天一行
                await db.execute(
                    "REPLACE INTO records (user_id, nickname, length, record_date) VALUES (?, ?, ?, ?)",
                    (user_id, nickname, length, today)
                )
                await db.commit()

        msg = f"{nickname} 今天的长度是 {length}cm！"
        if not is_new:
            msg = "（今日已锁定）" + msg
            
        yield event.plain_result(msg)

    @filter.command("长度排行")
    async def handle_rank(self, event: AstrMessageEvent):
        await self._init_db()
        today = datetime.now().strftime("%Y-%m-%d")

        async with aiosqlite.connect(self.db_path) as db:
            # 利用 SQL 引擎进行排序，比 Python 排序效率更高
            async with db.execute(
                "SELECT nickname, length FROM records WHERE record_date = ? ORDER BY length DESC", 
                (today,)
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            yield event.plain_result("今天还没有人参与测试哦~")
            return

        chunk_size = 15
        header = "🏆 今日长度排行榜 (SQL) 🏆\n" + "—" * 20 + "\n"
        
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            rank_text = header if i == 0 else ""
            for index, (nick, l_val) in enumerate(chunk, start=i + 1):
                rank_text += f"{index}. {nick}: {l_val}cm\n"
            
            yield event.plain_result(rank_text.strip())