# -*- coding: utf-8 -*-
"""19.0.2.17.0: the technician's Start work starts the diagnosis, and the customer's
"inspecting your device" WhatsApp says the safety check was done ({safety}: gloves, mask, ...).
Only a text nobody edited changes (line ends ignored: the starter text was loaded with CRLF)."""

OLD = "Hi {name}, our technician is inspecting your device 🔍 (order {order}).\nTrack it: {track_url}"
NEW = "Hi {name}, our technician is inspecting your device 🔍 (order {order}).{safety}\nTrack it: {track_url}"


def migrate(cr, version):
    cr.execute("""
        UPDATE online_service_message SET body = %s
         WHERE key = 'inspection' AND btrim(replace(body, E'\\r', ''), E'\\n ') = %s
    """, (NEW, OLD))
