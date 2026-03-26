import random
import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register, StarTools
import astrbot.api.message_components as Comp

@register("today_length", "GeMio", "数据库核心版：今日长度", "2.0.0")
class TodayLengthPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir("today_length")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "lengths.db"
        
        # 初始化数据库表
        self._init_db()

    def _init_db(self):
        """初始化 SQL 表结构"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # 创建记录表：uid (主键), nickname, length, date
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS length_records (
                    uid TEXT PRIMARY KEY,
                    nickname TEXT,
                    length REAL,
                    record_date TEXT
                )
            ''')
            conn.commit()

    async def _execute_query(self, query: str, params: tuple = (), fetch: str = None):
        """数据库操作的异步封装（防止阻塞主循环）"""
        def _run():
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query, params)
                if fetch == "one":
                    return cursor.fetchone()
                if fetch == "all":
                    return cursor.fetchall()
                conn.commit()
                return None
        return await asyncio.to_thread(_run)

    async def _get_user_nickname(self, event: AstrMessageEvent, user_id: str) -> str:
        """安全获取昵称逻辑"""
        try:
            safe_uid = int(user_id) if user_id.isdigit() else user_id
            group_id = event.get_group_id()
            if group_id:
                safe_gid = int(group_id) if str(group_id).isdigit() else group_id
                resp = await event.bot.get_group_member_info(group_id=safe_gid, user_id=safe_uid)
                if resp:
                    return resp.get("card") or resp.get("nickname") or user_id
            resp = await event.bot.get_stranger_info(user_id=safe_uid)
            return resp.get("nickname") or user_id
        except:
            return user_id

    @filter.command("今日长度")
    async def handle_length(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        today_str = datetime.now().strftime("%Y-%m-%d")

        # 1. 查询数据库是否存在今日记录
        row = await self._execute_query(
            "SELECT * FROM length_records WHERE uid = ?", 
            (user_id,), 
            fetch="one"
        )

        # 2. 逻辑判断：如果日期匹配，则锁定
        if row and row['record_date'] == today_str:
            yield event.chain_result([
                Comp.At(qq=user_id),
                Comp.Plain(f" （今日已锁定）你的长度为：{row['length']} cm")
            ])
            return

        # 3. 否则，生成新数据（网络 I/O 在外）
        nickname = await self._get_user_nickname(event, user_id)
        length = round(random.uniform(1, 20), 2)

        # 4. 插入或更新数据库 (UPSERT 语义)
        await self._execute_query(
            '''INSERT OR REPLACE INTO length_records (uid, nickname, length, record_date) 
               VALUES (?, ?, ?, ?)''',
            (user_id, nickname, length, today_str)
        )

        yield event.chain_result([
            Comp.At(qq=user_id),
            Comp.Plain(f" {nickname}，你的今日长度为：{length} cm")
        ])

    @filter.command("长度排行")
    async def handle_rank(self, event: AstrMessageEvent):
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # SQL 的强大之处：直接一行代码完成 排序 + 过滤
        rows = await self._execute_query(
            "SELECT nickname, length FROM length_records WHERE record_date = ? ORDER BY length DESC",
            (today_str,),
            fetch="all"
        )

        if not rows:
            yield event.plain_result("今日榜单尚无记录。")
            return

        header = f"📊 数据库版·全员榜 ({today_str})\n━━━━━━━━━━━━━━\n"
        lines = []
        for i, row in enumerate(rows, 1):
            medal = "🥇 " if i == 1 else "🥈 " if i == 2 else "🥉 " if i == 3 else f"[{i}] "
            lines.append(f"{medal}{row['nickname']}：{row['length']} cm")

        # 分片发送
        chunk_size = 15
        for i in range(0, len(lines), chunk_size):
            chunk = lines[i:i + chunk_size]
            output = header + "\n".join(chunk) if i == 0 else "\n".join(chunk)
            yield event.plain_result(output)

    def terminate(self):
        logger.info("[TodayLength] 数据库插件已安全卸载")