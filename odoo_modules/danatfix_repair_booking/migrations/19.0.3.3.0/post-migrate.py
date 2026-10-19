# -*- coding: utf-8 -*-
"""19.0.3.3.0: each alarm has its own settings tab. The "visit time booked" alarm starts
with what both alarms shared until now (ring, pause, who hears it)."""


def migrate(cr, version):
    cr.execute("""
        UPDATE danatfix_booking_settings
           SET slot_ring_seconds = ring_seconds, slot_repeat_seconds = repeat_seconds,
               new_alarm_on = TRUE, slot_alarm_on = TRUE
    """)
    cr.execute("""
        INSERT INTO danatfix_booking_slot_alarm_user_rel (settings_id, user_id)
        SELECT settings_id, user_id FROM danatfix_booking_alarm_user_rel
        ON CONFLICT DO NOTHING
    """)
