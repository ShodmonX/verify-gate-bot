"""seed prohibited words

Revision ID: 0004_seed_prohibited_words
Revises: 0003_prohibited_words
Create Date: 2026-01-30 00:00:00.000000

"""
from typing import Sequence, Union
import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

revision: str = "0004_seed_prohibited_words"
down_revision: Union[str, None] = "0003_prohibited_words"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WORDS = ['Ahmoq', 'Am', 'Amcha', 'Befarosat', 'Blyat', 'Buvini ami', "Cho'choq", 'Dalban', 'Dalbayob', 'Dalbayop', 'Dnx', 'Dovdir', 'Ey qetoq', 'Foxisha', 'Fuck', 'Fuck you', 'Gandon', 'Gotalak', 'Haromi', 'Hunasa', 'Iflos', 'Iplos', 'Isqirt', 'Jalab', 'Jalap', 'Jalla', 'Jallab', 'Jallap', 'Jinni', 'Jipiriq', 'Kispurush', "Ko't", 'Kot', 'Kotinga', 'Koʻt', 'Lox', 'Manjalaqi', 'Maraz', 'Mol miyya', 'Om', 'Onangni sikay', 'Onenei ami', 'Opangni omiga ske', 'Pasholak', 'Pidaraz', 'Pidr', 'Pipez', 'Pizdes', 'Poxuy', 'Poxxuy', 'Pzdc', 'Pzds', 'Pzdss', 'Qanchiq', 'Qanciq', 'Qanjiq', 'Qetoq', "Qo'taq", 'Qotaqxor', 'Qoto', 'Qotoq', 'Qotoqbosh', 'Qo’toq', 'Seks', 'Sen qishloqlisan', 'Sik', 'Sikaman', 'Sikay', 'Sikdim', 'Skay', 'Ske', 'Suchka', 'Suka', 'Tashoq', 'Tashshoq', "Tashshoq sho'rva", 'Tashshoq sho’rva', 'Tente', 'Xaromi', 'Ya yebal tebya', 'Yban', 'Ybat', 'Yeban', 'Yebanutiy', 'Yebat', 'Yiban', 'Yobbana', 'Zaybal', 'ahmoq', 'ahuel', 'am', 'ambaliq', 'amcha', 'aminga', 'amingga ske', 'axmoq', 'basharenga qotogm', 'bich', 'bitch', 'ble', 'blet', "bo'qidish", "bo'qkalla", 'boq', 'buvini ami', 'buvini amiga ske', 'chmo', "cho'choq", 'chumo', 'dabba', 'dalban', 'dalbayob', 'daun', 'dinnaxuy', 'foxisha qanchiq', 'fuck', 'fuck off', 'fucking', 'gandon', 'garang', 'gay', 'gey', 'gnida', 'haromi', 'hunasa', 'idi naxuy', 'iflos', 'it', 'itbet', 'jala', 'jala ble', 'jalaaap', 'jalab', 'jalap', 'jalla', 'jallap', 'jentra miyya', 'kashanda', "ko't", 'kot', 'lox', 'mol', 'nedagon', 'nigga', 'nigger', 'om', 'onangni', 'onangni ami', 'onangni sikay', 'oneni ami', 'oom', 'oʻl', 'p1zdes', 'pashol na xuy', 'pidaras', 'pidaraz', 'pidr', 'pizda', 'pizdes', 'qanjiq', "qo'toq", "qo'toqbosh", 'qotaq', 'qoto', 'qotoq', 'qutoq', 'seks', 'seksi baby', 'sex', 'sexy woman', 'shavqatsiz', 'sikay', 'sike', 'sikish', 'siktim', 'sikvoti', 'skay', 'ske', 'skey', 'suchka', 'suka', 'sukka', 'tashsho', 'tupoy', 'tvar', 'tvariddin', 'wtf', 'xaromi', 'xuyeplet', 'xuyesos', 'xuyila', 'yban', 'yeban', 'yebanashka', 'yebat', 'yebbat', 'yeblan', 'yebnu', 'yebu', 'yetim', 'yetm', 'yiban', 'yibanat']


def normalize_word(word: str) -> str:
    word = word.strip().lower()
    return " ".join(word.split())


def upgrade() -> None:
    conn = op.get_bind()
    total = conn.execute(sa.text("SELECT COUNT(*) FROM prohibited_words")).scalar()
    if total and int(total) > 0:
        return

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    rows = []
    for raw in WORDS:
        norm = normalize_word(raw)
        if not norm or len(norm) < 3:
            continue
        match_type = "PHRASE" if " " in norm else "TOKEN"
        rows.append(
            {
                "word": norm,
                "original": raw,
                "enabled": True,
                "match_type": match_type,
                "created_at": now,
                "created_by": 0,
            }
        )

    if rows:
        table = sa.table(
            "prohibited_words",
            sa.column("word"),
            sa.column("original"),
            sa.column("enabled"),
            sa.column("match_type"),
            sa.column("created_at"),
            sa.column("created_by"),
        )
        stmt = pg_insert(table).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["word"])
        conn.execute(stmt)


def downgrade() -> None:
    conn = op.get_bind()
    for raw in WORDS:
        norm = normalize_word(raw)
        if not norm:
            continue
        conn.execute(
            sa.text("DELETE FROM prohibited_words WHERE word = :word"),
            {"word": norm},
        )
