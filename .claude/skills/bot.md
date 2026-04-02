# Skill: Aiogram — контекстные кнопки из карточки инцидента

## Формирование кнопок из Incident
```python
# app/bot/callbacks.py
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
import json, redis.asyncio as aioredis
from app.config import settings

def incident_keyboard(thread_id: str, incident: dict) -> InlineKeyboardMarkup:
    """Кнопки из dangerous_actions карточки инцидента."""
    builder = InlineKeyboardBuilder()

    for i, action in enumerate(incident.get("dangerous_actions", [])):
        # callback_data: "action:{thread_id}:{action_index}"
        builder.button(
            text=action["label"],
            callback_data=f"action:{thread_id}:{i}",
        )

    builder.button(
        text="🔕 Игнорировать",
        callback_data=f"ignore:{thread_id}",
    )
    builder.adjust(1)  # одна кнопка в строку
    return builder.as_markup()
```

## Уведомление при interrupt
```python
# app/bot/handlers.py
async def notify_incident(chat_id: int, thread_id: str, interrupt_data: dict):
    incident = interrupt_data["incident"]

    text = (
        f"<b>{'🔴' if incident['severity'] == 'critical' else '🟡'} "
        f"{incident['host']} — {incident['problem_type']}</b>\n\n"
        f"{incident['evidence']}"
    )

    keyboard = incident_keyboard(thread_id, incident)
    msg = await bot.send_message(chat_id, text, reply_markup=keyboard)

    # Сохранить: message_id → thread_id + incident
    r = aioredis.from_url(settings.REDIS_URL)
    await r.set(
        f"tg_thread:{msg.message_id}",
        json.dumps({"thread_id": thread_id, "incident": incident}),
        ex=3600,
    )
    await r.aclose()
```

## Callback — resume с выбранным действием
```python
@router.callback_query(lambda c: c.data.startswith("action:"))
async def on_action(callback: CallbackQuery):
    _, thread_id, action_idx = callback.data.split(":", 2)
    action_idx = int(action_idx)

    r = aioredis.from_url(settings.REDIS_URL)
    raw = await r.get(f"tg_thread:{callback.message.message_id}")
    await r.aclose()

    if not raw:
        await callback.answer("⏰ Истёк таймаут", show_alert=True)
        return

    data = json.loads(raw)
    incident = data["incident"]
    chosen_action = incident["dangerous_actions"][action_idx]

    # Resume графа с выбранным runbook
    graph = await get_analyze_graph()
    config = {"configurable": {"thread_id": thread_id}}

    result = await graph.ainvoke(
        Command(resume={
            "runbook": chosen_action["runbook"],
            "params":  chosen_action["params"],
        }),
        config=config,
    )

    await callback.message.edit_reply_markup(reply_markup=None)
    # Результат runbook придёт отдельным сообщением из execute_node
    await callback.answer("⚙️ Выполняю...")

@router.callback_query(lambda c: c.data.startswith("ignore:"))
async def on_ignore(callback: CallbackQuery):
    _, thread_id = callback.data.split(":", 1)
    graph = await get_analyze_graph()
    config = {"configurable": {"thread_id": thread_id}}
    await graph.ainvoke(Command(resume={"runbook": None}), config=config)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply("🔕 Проигнорировано")
    await callback.answer()
```

## Правила

- Кнопки генерируются из `dangerous_actions` карточки — не хардкодить
- `callback_data` содержит `thread_id` и индекс action — не runbook name (длина ограничена 64 байт)
- `safe_actions` выполняются без кнопок — автоматически или по запросу
- Один инцидент = одно сообщение = один interrupt
- Если несколько инцидентов на хосте — отдельные сообщения, отдельные thread_id