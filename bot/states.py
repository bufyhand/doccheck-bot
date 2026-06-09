from aiogram.fsm.state import State, StatesGroup


class CheckStates(StatesGroup):
    waiting_order = State()
    waiting_invoice = State()

