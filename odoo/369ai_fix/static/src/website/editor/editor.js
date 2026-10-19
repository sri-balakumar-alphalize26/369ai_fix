/** @odoo-module */
/**
 * Fix Website editor: the Home page, the Services page or the Info pages, drawn on the left
 * the way the website draws them (same colours, fonts and layout), with a panel on the right
 * that edits whatever you click. Changes show at once and are saved a moment after you stop
 * typing (see save_queue.js). Drag a section to reorder it, press the eye to hide it. Hover a
 * field in the panel and the part of the page it changes lights up.
 */
import { Component, markup, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useSortable } from "@web/core/utils/sortable_owl";
import { getDataURLFromFile } from "@web/core/utils/urls";
import { _t } from "@web/core/l10n/translation";
import { Layout } from "@web/search/layout";
import { useSaveQueue } from "./save_queue";

const SITE = "online.service.site";
const M = {
    site: SITE, section: "fix.home.section", line: "fix.home.line", page: "fix.home.page",
    link: "fix.site.link", branch: "fix.site.branch", zone: "fix.coverage.zone", area: "fix.coverage.area",
    faq: "fix.site.faq", info: "fix.site.page", cat: "device.category", product: "product.template", brand: "device.brand",
    item: "fix.site.item",
};
// Pop-ups & chat: the welcome pop-up choices, the four item lists, the prize icons and what a chat chip can do
const WELCOME_TYPES = [["slot", "Book your slot slider", "fa-calendar-check-o"], ["spin", "Spin & Win wheel", "fa-gift"], ["flash", "Flash offer", "fa-bolt"], ["none", "Nothing", "fa-ban"]];
const ITEM_KINDS = { wheel: "Prize", reply: "Quick reply", slide: "Slide", tile: "Tile" };
const ICONS = [["diag", "Magnifier (diagnosis)"], ["pick", "Scooter (pickup)"], ["clean", "Sparkle (cleaning)"], ["fast", "Bolt (priority)"], ["data", "Cloud (backup)"], ["guard", "Shield (screen guard)"]];
const INTENTS = [["book", "Book a repair"], ["area", "Check my area"], ["price", "Prices"], ["time", "How long"], ["contact", "Branches & contact"], ["hours", "Opening hours"], ["human", "Talk to a person"], ["menu", "Back to the menu"]];
// what the website puts in place of the words in curly brackets (the preview uses the same)
const LEGEND = {
    site: "the website name", code: "the offer or prize code", fee: "the visit fee line", hours: "the opening hours", device: "the device type",
    issue: "the problem chosen", price: "the price line", area: "the area typed", branches: "the branch names", phone: "the phone number",
    email: "the email", doorstep: "the visit time", pickup: "the lab time", slide: "the slide title", contact: "the number or email typed",
};

// ------------------------------------------------------------------ what every field is
// label = where it shows, in plain words · hint = what it does, with an example · type = text | area | number | int | bool | select
const FIELD_HELP = {
    "site.name": { label: "Website name", hint: "The name in the header, the footer and WhatsApp messages · e.g. Danat Fix" },
    "site.tagline": { label: "Tagline", hint: "Under the name in the browser tab and in the footer · e.g. Electronics repair at your doorstep" },
    "site.header_cta": { label: "Orange button (top right)", hint: "Empty = Book a repair" },
    "site.header_cta_link": { label: "The orange button opens", hint: "A page on the site · e.g. /services#catalog" },
    "site.contact_phone": { label: "Phone", hint: "Footer and Contact page, as typed · e.g. +968 7832 3116" },
    "site.contact_whatsapp": { label: "WhatsApp number", hint: "Digits with the country code, no + · every WhatsApp button opens it · e.g. 96878323116" },
    "site.contact_email": { label: "Email", hint: "Footer and Contact page" },
    "site.contact_address": { label: "Address", hint: "Contact page · e.g. Computer Street, Ruwi, PO Box 502, PC 118, Sultanate of Oman", type: "area" },
    "site.opening_hours": { label: "Opening hours", hint: "Contact page · e.g. Sat–Thu 9:00–21:00" },
    "site.since_year": { label: "Since (year)", hint: "Used in \"since 2003\" lines · e.g. 2003" },
    "site.social_facebook": { label: "Facebook page", hint: "Full address; empty = the Facebook icon is hidden" },
    "site.social_instagram": { label: "Instagram page", hint: "Full address; empty = the Instagram icon is hidden" },
    "site.footer_about": { label: "About text (footer)", hint: "The paragraph under the logo in the footer", type: "area" },
    "site.footer_copyright": { label: "Copyright line", hint: "Bottom left of every page · {year} becomes the current year · e.g. © {year} Danat Fix. All rights reserved." },
    "site.footer_credit": { label: "Credit line", hint: "Bottom right of every page · e.g. Site developed and maintained by alphalize" },
    "site.svc_eyebrow": { label: "Small line above the title", hint: "Services page, top banner · e.g. Services" },
    "site.svc_title": { label: "Big title (white part)", hint: "e.g. Doorstep repair," },
    "site.svc_title2": { label: "Big title (green part)", hint: "e.g. on the spot or in our lab." },
    "site.svc_lead": { label: "Intro under the title", hint: "The counts (device types, brands, models) are added after it automatically", type: "area" },
    "site.svc_modes_eyebrow": { label: "Small line above step 1", hint: "e.g. How it works" },
    "site.svc_modes_title": { label: "Step 1 title", hint: "e.g. We come to you first" },
    "site.svc_fee_label": { label: "Fee label", hint: "Under the flow card, before the price · e.g. Visit fee" },
    "site.cov_eyebrow": { label: "Small line above step 2", hint: "e.g. Check your area" },
    "site.cov_title": { label: "Step 2 title", hint: "e.g. Where we cover" },
    "site.cov_trust": { label: "Trust points under the areas", hint: "One per line · {price} becomes the price shown · e.g. Diagnosis before any work", type: "area" },
    "sec.*.eyebrow": { label: "Small line above the title", hint: "Short, in green capitals · e.g. Testimonials" },
    "sec.*.title": { label: "Title", hint: "The section heading" },
    "sec.*.title2": { label: "Title (green part)", hint: "Shown after the title in the accent colour" },
    "sec.*.subtitle": { label: "Line under the title", hint: "" },
    "sec.*.text": { label: "Text", hint: "A short paragraph under the title", type: "area" },
    "sec.*.button1": { label: "Button", hint: "" },
    "sec.*.button1_link": { label: "The button opens", hint: "A page on the site · e.g. /services#catalog" },
    "sec.hero.eyebrow": { label: "Small line above the big title", hint: "Green capitals · e.g. Doorstep electronics repair · Oman" },
    "sec.hero.title": { label: "Big title (white part)", hint: "e.g. Your Technology." },
    "sec.hero.title2": { label: "Big title (green part)", hint: "e.g. Fixed Right." },
    "sec.hero.subtitle": { label: "Devices line", hint: "Under the big title · e.g. Phone • Laptop • Computer • Printer • CCTV • Networking" },
    "sec.hero.button1": { label: "Green button", hint: "e.g. Book Your Slot" },
    "sec.hero.button1_link": { label: "The green button opens", hint: "e.g. #book-services (the device tiles) or /services#catalog" },
    "sec.hero.button2": { label: "WhatsApp button", hint: "Opens WhatsApp with the website's number · e.g. WhatsApp us" },
    "sec.hero.video_url": { label: "Background video", hint: "A video file on the site · e.g. /media/kling.mp4 · empty = the still picture only" },
    "sec.services.badge": { label: "Small green pill above the title", hint: "Empty = \"N services · doorstep\"" },
    "sec.services.title": { label: "Title", hint: "e.g. What can we fix for you?" },
    "sec.services.subtitle": { label: "\"Most booked\" title", hint: "e.g. Most booked repairs" },
    "sec.services.text": { label: "\"Most booked\" line", hint: "Under that title · e.g. Doorstep or pickup · price confirmed before any work", type: "area" },
    "sec.services.button1": { label: "Link text at the bottom", hint: "e.g. View all services" },
    "sec.services.button1_link": { label: "The link opens", hint: "e.g. /services#all" },
    "sec.modes.button1": { label: "Link text at the bottom of the card", hint: "e.g. Check your area →" },
    "sec.modes.button1_link": { label: "The link opens", hint: "e.g. /services#coverage" },
    "sec.brands.eyebrow": { label: "Small green pill above the title", hint: "e.g. Brands we repair" },
    "sec.brands.title": { label: "Title", hint: "e.g. All the big names," },
    "sec.brands.title2": { label: "Title (green part)", hint: "e.g. one trusted fix." },
    "sec.reviews.text": { label: "Intro", hint: "Under the title · e.g. Doorstep visits, pickups and installs across Oman — in our customers’ words.", type: "area" },
    "sec.milestones.text": { label: "Note under the list", hint: "e.g. Years marked “TBC” are waiting for confirmation.", type: "area" },
    "sec.partners.title": { label: "Title (green part)", hint: "e.g. Leading brands," },
    "sec.partners.title2": { label: "Title", hint: "e.g. in safe hands" },
    "sec.cta.title": { label: "Title", hint: "e.g. Need a" },
    "sec.cta.title2": { label: "Title (light part)", hint: "e.g. repair or service?" },
    "sec.cta.button1": { label: "White button", hint: "e.g. Book a repair" },
    "line.hero.value": { label: "Number", hint: "e.g. 36+" },
    "line.hero.name": { label: "Label under the number", hint: "e.g. services" },
    "line.modes.name": { label: "Title", hint: "" },
    "line.modes.extra": { label: "Short note", hint: "Line 1: under the title · line 2: the small note · e.g. Price confirmed with you first" },
    "line.modes.value": { label: "Time", hint: "e.g. Technician at your door in about 60 minutes" },
    "line.modes.text": { label: "Steps, one per line", hint: "Line 1: the last step is the \"fixed on the spot\" branch", type: "area" },
    "line.reviews.name": { label: "Customer", hint: "" },
    "line.reviews.value": { label: "Area", hint: "e.g. Qurum" },
    "line.reviews.extra": { label: "What was repaired", hint: "e.g. iPhone screen replacement" },
    "line.reviews.stars": { label: "Stars (1–5)", hint: "", type: "number" },
    "line.reviews.text": { label: "The review", hint: "", type: "area" },
    "line.milestones.value": { label: "Year", hint: "e.g. 2003, or Year TBC" },
    "line.milestones.name": { label: "Title", hint: "e.g. First store opens on Computer Street, Ruwi" },
    "line.milestones.text": { label: "Text", hint: "", type: "area" },
    "line.partners.name": { label: "Partner", hint: "Shown when there is no logo" },
    "line.partners.link": { label: "Web address", hint: "Optional · the logo links there" },
    "line.cta.name": { label: "Trust point", hint: "e.g. Since 2003" },
    "popular.name": { label: "Label", hint: "e.g. Laptop Repair" },
    "popular.link": { label: "Opens", hint: "e.g. /services?cat=laptop#catalog" },
    "link.name": { label: "Label", hint: "" },
    "link.link": { label: "Opens", hint: "A page on the site (/services) or a full web address" },
    "branch.name": { label: "Branch", hint: "e.g. Ruwi" },
    "branch.address": { label: "Address, one line per row", hint: "", type: "area" },
    "branch.phones": { label: "Phones", hint: "Comma-separated · e.g. +968 9792 3077, +968 9792 2924" },
    "branch.map_query": { label: "Map search", hint: "What Google Maps looks up for \"Get directions\" · e.g. Computer Street, Ruwi, Muscat, Oman" },
    "zone.name": { label: "Zone", hint: "A branch in brackets shows under it · e.g. Muscat (Ruwi branch)" },
    "faq.name": { label: "Question", hint: "" },
    "faq.answer": { label: "Answer", hint: "{price} becomes the price shown", type: "area" },
    "page.name": { label: "Page title", hint: "In the footer column and at the top of the page" },
    "page.slug": { label: "Web address", hint: "The page opens at /page/<this> · letters, numbers and dashes", now: true },
    "brand.caption": { label: "Caption under the logo", hint: "In the brands strip on the home page · e.g. iPhone · iPad · Mac" },
    "brand.color": { label: "Brand colour", hint: "Behind the name when there is no logo · e.g. #1428A0" },
    // ---- Pop-ups & chat
    "site.ann_show": { label: "Announcement bar", hint: "Off = no bar at the top of the site", type: "bool", on: "Shown at the top of every page", off: "Hidden" },
    "site.ann_text": { label: "Bar text", hint: "Scrolls across the dark bar at the very top · e.g. Doorstep repair across Oman — free diagnosis this week" },
    "site.ann_button": { label: "Bar button", hint: "The small green pill after the text · e.g. Book now →" },
    "site.ann_link": { label: "The bar button opens", hint: "A page on the site · e.g. /services#catalog" },
    "site.ann_speed_s": { label: "Scroll time (seconds)", hint: "One full pass of the text; bigger = slower · e.g. 30", type: "int" },
    "site.welcome_popup": { label: "Which pop-up opens first", hint: "A moment after a visitor arrives. On the site, ?offer=spin or ?offer=flash forces one", type: "select", options: WELCOME_TYPES },
    "site.welcome_delay_ms": { label: "Opens after (milliseconds)", hint: "1000 = one second · e.g. 1500", type: "int" },
    "site.welcome_flash_delay_ms": { label: "Flash offer opens after (milliseconds)", hint: "Only when the flash offer is the welcome pop-up · e.g. 4000", type: "int" },
    "site.welcome_snooze_days": { label: "Stay away for (days)", hint: "After the visitor closes it with ×, no welcome pop-up on that browser for this long · e.g. 30", type: "int" },
    "site.flash_badge": { label: "Small red badge", hint: "Top of the card · e.g. Flash offer" },
    "site.flash_title": { label: "Offer title", hint: "e.g. Free diagnosis this week" },
    "site.flash_body": { label: "Offer text", hint: "{fee} becomes the visit fee line · e.g. Book a doorstep visit and the check-up is on us. {fee}.", type: "area" },
    "site.flash_code": { label: "Offer code", hint: "The visitor taps it to copy · e.g. 369FIX" },
    "site.flash_button": { label: "Green button", hint: "e.g. Book with offer" },
    "site.flash_button_link": { label: "The green button opens", hint: "e.g. /services#catalog" },
    "site.flash_wa_button": { label: "WhatsApp button", hint: "e.g. WhatsApp us" },
    "site.flash_wa_msg": { label: "WhatsApp message", hint: "Pre-written in WhatsApp · e.g. Hello {site} — I'd like to use code {code}" },
    "site.flash_later": { label: "Close link", hint: "Under the buttons · e.g. No thanks" },
    "site.cookie_show": { label: "Cookie notice", hint: "Off = no cookie notice", type: "bool", on: "Shown on the first visit", off: "Hidden" },
    "site.cookie_title": { label: "Title", hint: "e.g. We use cookies" },
    "site.cookie_text": { label: "Text", hint: "e.g. Only to remember your theme, area and choices on this site. No ads, no tracking.", type: "area" },
    "site.cookie_decline": { label: "Decline button", hint: "e.g. Decline" },
    "site.cookie_accept": { label: "Accept button", hint: "e.g. Accept" },
    "site.cookie_delay_ms": { label: "Slides in after (milliseconds)", hint: "e.g. 1200", type: "int" },
    "site.wheel_tab": { label: "Side tab", hint: "The gift tab on the left edge of every page · e.g. Spin & Win" },
    "site.wheel_eyebrow": { label: "Small gold line above the title", hint: "e.g. ✦ {site} rewards ✦" },
    "site.wheel_title": { label: "Title", hint: "e.g. Spin &" },
    "site.wheel_title2": { label: "Title (gold part)", hint: "e.g. Win" },
    "site.wheel_subtitle": { label: "Line under the title", hint: "e.g. Every slice is a free extra on your next repair." },
    "site.wheel_spin": { label: "Spin button", hint: "e.g. Spin the wheel" },
    "site.wheel_later": { label: "Close link", hint: "e.g. Maybe later" },
    "site.wheel_won": { label: "\"You won\" line", hint: "Above the prize after the spin · e.g. 🎉 You won" },
    "site.wheel_note": { label: "Note under the code", hint: "e.g. Show this code when you book. Valid on your next repair." },
    "site.wheel_book": { label: "Book button", hint: "e.g. Book now" },
    "site.wheel_wa": { label: "WhatsApp button", hint: "e.g. WhatsApp us" },
    "site.wheel_wa_msg": { label: "WhatsApp message", hint: "{code} = the prize code · e.g. Hello {site} — I won on the spin wheel, code: {code}" },
    "site.bot_name": { label: "Assistant name", hint: "Top of the chat window · e.g. {site} Assistant" },
    "site.bot_status": { label: "Line under the name", hint: "e.g. Automated help · replies instantly" },
    "site.bot_greeting": { label: "First message", hint: "e.g. Hi 👋 I'm the {site} assistant. I can help you book a repair, check your area or find a branch.", type: "area" },
    "site.bot_placeholder": { label: "Typing box hint", hint: "e.g. Ask about a repair, area or price…" },
    "site.bot_tip": { label: "Chat button tip", hint: "Shows when hovering the round chat button · e.g. Ask us anything" },
    "site.bot_wa_tip": { label: "WhatsApp button tip", hint: "e.g. WhatsApp us" },
    "site.bot_wa_msg": { label: "WhatsApp button message", hint: "e.g. Hello {site} — I need help with a repair." },
    "site.bot_a_book": { label: "\"Book a repair\"", hint: "Then the device types are offered · e.g. Great! Which device needs fixing?", type: "area" },
    "site.bot_a_dev": { label: "Device chosen", hint: "{device} = the device type · e.g. What's the problem with your {device}?", type: "area" },
    "site.bot_a_iss": { label: "Problem chosen", hint: "{issue}, {device}, {price} · e.g. Got it — {issue} for {device}. {price} Tap below and your booking message is ready to send.", type: "area" },
    "site.bot_a_area": { label: "\"Check my area\"", hint: "e.g. Type your area name below (for example Qurum or Sohar) and I'll check.", type: "area" },
    "site.bot_a_found": { label: "Area found", hint: "{area} = the area typed · e.g. ✅ Yes, we cover {area}. Want to book a repair there?", type: "area" },
    "site.bot_a_price": { label: "\"Prices\"", hint: "{fee} = the visit fee line", type: "area" },
    "site.bot_a_time": { label: "\"How long?\"", hint: "{doorstep} = the visit time, {pickup} = the lab time · e.g. Our technician comes to you first: {doorstep}. If it needs a part or more work it goes to our lab: {pickup}.", type: "area" },
    "site.bot_a_contact": { label: "\"Branches & contact\"", hint: "{branches}, {phone}, {email} · e.g. We have branches in {branches}. 📞 {phone} ✉️ {email}", type: "area" },
    "site.bot_a_hours": { label: "\"Opening hours\"", hint: "{hours} = the opening hours in the footer · e.g. We're open {hours}.", type: "area" },
    "site.bot_a_human": { label: "\"Talk to a person\"", hint: "A WhatsApp button follows · e.g. Sure — our team replies on WhatsApp.", type: "area" },
    "site.bot_a_menu": { label: "Back to the menu", hint: "e.g. How else can I help?", type: "area" },
    "site.bot_a_fallback": { label: "Not understood", hint: "A WhatsApp button with the question follows · e.g. I'm not sure about that one — our team can help on WhatsApp.", type: "area" },
    "site.eng_eyebrow": { label: "Small line on every slide", hint: "e.g. Book your slot" },
    "site.eng_title2": { label: "Generic title (green part)", hint: "For a device type without a slide of its own: its name, then this · e.g. repair at your door" },
    "site.eng_perks": { label: "Generic perks", hint: "One per line, for a device type without a slide of its own · e.g. Expert technicians", type: "area" },
    "site.eng_from_label": { label: "Price label", hint: "Before the lowest price of the device type · e.g. Starting from" },
    "site.eng_slide_ms": { label: "Next slide after (milliseconds)", hint: "e.g. 3500", type: "int" },
    "site.eng_idle_s": { label: "Opens after idle (seconds)", hint: "No mouse, scroll, key or touch for this long · once per visit · e.g. 35", type: "int" },
    "site.eng_still_s": { label: "Opens after still (seconds)", hint: "Cursor still for this long, or leaving through the top of the window · once per visit · e.g. 15", type: "int" },
    "site.eng_wa_msg": { label: "Form WhatsApp message", hint: "{slide} = the slide shown, {contact} = the number or email typed · e.g. Hi {site}, I want to book {slide}. My contact: {contact}" },
    "site.eng_form_pill": { label: "Green pill", hint: "e.g. Book instantly on WhatsApp" },
    "site.eng_form_title": { label: "Form title", hint: "e.g. Book your slot" },
    "site.eng_form_subtitle": { label: "Line under the form title", hint: "e.g. Share your number or email and we'll start the booking on WhatsApp." },
    "site.eng_form_privacy": { label: "Privacy line", hint: "Under the send button · e.g. No spam. We only use your number to confirm the booking." },
    "site.eng_form_send": { label: "Send button", hint: "e.g. Send on WhatsApp" },
    "site.eng_form_all": { label: "\"All services\" link", hint: "e.g. View all services" },
    "site.eng_form_all_link": { label: "The \"all services\" link opens", hint: "e.g. /services#all" },
    "site.eng_form_features": { label: "Three features at the bottom", hint: "One per line, title|small line · e.g. Quick Service|In most areas", type: "area" },
    "site.exit_title": { label: "Title", hint: "e.g. Leaving already? 👋" },
    "site.exit_status": { label: "Line under the title", hint: "e.g. We reply on WhatsApp" },
    "site.exit_text": { label: "Text above the tiles", hint: "e.g. What do you need fixed today? Tap one — we'll reply on WhatsApp." },
    "site.exit_button": { label: "WhatsApp button", hint: "e.g. Chat with us on WhatsApp" },
    "site.exit_wa_msg": { label: "WhatsApp button message", hint: "e.g. Hi {site}, I need help with a repair." },
    "site.exit_tile_msg": { label: "Tile message", hint: "{device} = the device type of the tile · e.g. Hi {site}, I need help with my {device}." },
    "site.exit_link": { label: "The bottom link opens", hint: "e.g. /#book-services" },
    "site.exit_link_label": { label: "Bottom link", hint: "e.g. See all services →" },
    "item.wheel.name2": { label: "Word above", hint: "Small capitals · e.g. Free" },
    "item.wheel.name": { label: "Word on the slice", hint: "Big · e.g. Diagnosis" },
    "item.wheel.text": { label: "Prize in full", hint: "Shown after the spin · e.g. Free diagnosis" },
    "item.wheel.code": { label: "Prize code", hint: "The visitor shows it when booking · e.g. SPIN-DIAG" },
    "item.wheel.color": { label: "Slice colour", hint: "e.g. #f5b400, or var(--violet) for the site's green" },
    "item.wheel.color2": { label: "Text colour", hint: "e.g. #fff or #10241a" },
    "item.reply.name": { label: "Chip", hint: "e.g. 🔧 Book a repair" },
    "item.slide.name": { label: "Title", hint: "e.g. Mobile" },
    "item.slide.name2": { label: "Title (green part)", hint: "e.g. Repair" },
    "item.slide.text": { label: "Pitch", hint: "Under the title · e.g. Screen, battery, charging, camera and more – quick and reliable service.", type: "area" },
    "item.slide.text2": { label: "Perks, one per line", hint: "Four ticks · e.g. Genuine parts", type: "area" },
    "item.tile.name": { label: "Label", hint: "Empty = the device type's name · e.g. CCTV" },
};
const BRAND_FILTERS = [["all", "All"], ["nologo", "Missing logo"], ["strip", "In the strip"], ["nostrip", "Not in the strip"]];
const PHOTO_FILTERS = [["all", "All"], ["nophoto", "No photo"], ["few", "Fewer than 3 photos"], ["mb", "Most booked"]];

// The panels: a sentence about the part, then groups of fields
const SECTION_FORM = {
    hero: { about: "The dark banner at the top of the home page: title, buttons, search bar, counters and the Popular links.",
        groups: [{ title: "Wording", fields: ["eyebrow", "title", "title2", "subtitle"] }, { title: "Buttons", fields: ["button1", "button1_link", "button2"] }, { title: "Video and picture", fields: ["video_url"], image: true }] },
    services: { about: "\"What can we fix for you?\": the device tiles and the Most booked repairs.",
        groups: [{ title: "Wording", fields: ["badge", "title", "subtitle", "text", "button1", "button1_link"] }] },
    modes: { about: "How we fix it: the technician comes first; fixed on the spot, or to our lab and back. The same card shows on the Services page.",
        groups: [{ title: "Link", fields: ["button1", "button1_link"] }] },
    brands: { about: "The strip of brand logos. The logos are the brands ticked \"In the brands strip\" (Pictures ▸ Brand Logos).",
        groups: [{ title: "Wording", fields: ["eyebrow", "title", "title2"] }] },
    reviews: { about: "What our clients say: the review cards.", groups: [{ title: "Wording", fields: ["eyebrow", "title", "text"] }] },
    milestones: { about: "Our journey: the timeline.", groups: [{ title: "Wording", fields: ["eyebrow", "title", "text"] }] },
    partners: { about: "Trusted partners: their logos.", groups: [{ title: "Wording", fields: ["eyebrow", "title", "title2", "text"] }] },
    cta: { about: "The green closing banner near the bottom of the home page.", groups: [{ title: "Wording", fields: ["eyebrow", "title", "title2", "text"] }, { title: "Button", fields: ["button1", "button1_link"] }] },
};
const SITE_FORM = {
    header: { title: "Header", about: "The bar at the top of every page: name, menu and the orange button.",
        groups: [{ title: "Name", fields: ["name", "tagline"] }, { title: "Orange button", fields: ["header_cta", "header_cta_link"] }] },
    footer: { title: "Footer and contact details", about: "The bottom of every page, and the Contact page.",
        groups: [{ title: "Contact details", fields: ["contact_phone", "contact_whatsapp", "contact_email", "contact_address", "opening_hours", "since_year"] },
            { title: "Social links", fields: ["social_facebook", "social_instagram"] },
            { title: "Footer texts", fields: ["footer_about", "footer_copyright", "footer_credit"] }] },
    svc_head: { title: "Page heading", about: "The dark banner at the top of the Services page.", groups: [{ title: "Wording", fields: ["svc_eyebrow", "svc_title", "svc_title2", "svc_lead"] }] },
    flow: { title: "Step 1 · How we fix it", about: "The repair flow card. The card itself is shared with the home page.", groups: [{ title: "Wording", fields: ["svc_modes_eyebrow", "svc_modes_title", "svc_fee_label"] }] },
    coverage: { title: "Step 2 · Coverage areas", about: "The zones and areas the website says you reach, with the map.", groups: [{ title: "Wording", fields: ["cov_eyebrow", "cov_title", "cov_trust"] }] },
    // Pop-ups & chat. legend = the curly-bracket words the website fills in these texts
    ann: { title: "Announcement bar", about: "The thin dark bar that scrolls across the very top of every page. The visitor can close it; it is back on the next visit.",
        groups: [{ title: "The bar", fields: ["ann_show", "ann_text", "ann_button", "ann_link", "ann_speed_s"] }] },
    welcome: { title: "Welcome pop-up", about: "What opens a moment after a visitor arrives: the Book-your-slot slider, the Spin & Win wheel, the Flash offer, or nothing. Closing it with × keeps every welcome pop-up away for the days below.",
        groups: [{ title: "Which one, and when", fields: ["welcome_popup", "welcome_delay_ms", "welcome_flash_delay_ms", "welcome_snooze_days"] }] },
    flash: { title: "Flash offer", about: "The offer card with the countdown to midnight and a code to copy. Opens as the welcome pop-up when chosen, or from ?offer=flash.", legend: ["site", "code", "fee"],
        groups: [{ title: "Wording", fields: ["flash_badge", "flash_title", "flash_body", "flash_code"] }, { title: "Buttons", fields: ["flash_button", "flash_button_link", "flash_wa_button", "flash_wa_msg", "flash_later"] }] },
    wheel: { title: "Spin & Win", about: "The prize wheel: every slice wins. Opens from the gift tab on the left edge of every page, as the welcome pop-up when chosen, or from ?offer=spin.", legend: ["site", "code"],
        groups: [{ title: "Wording", fields: ["wheel_tab", "wheel_eyebrow", "wheel_title", "wheel_title2", "wheel_subtitle", "wheel_spin", "wheel_later"] }, { title: "After the spin", fields: ["wheel_won", "wheel_note", "wheel_book", "wheel_wa", "wheel_wa_msg"] }] },
    bot: { title: "Chat assistant", about: "The round chat button at the bottom right and its window. It answers from the site's own data (devices, prices, areas, branches); anything else goes to WhatsApp.", legend: ["site", "device", "issue", "price", "fee", "area", "branches", "phone", "email", "doorstep", "pickup", "hours"],
        groups: [{ title: "Window", fields: ["bot_name", "bot_status", "bot_greeting", "bot_placeholder", "bot_tip", "bot_wa_tip", "bot_wa_msg"] },
            { title: "Answers", fields: ["bot_a_book", "bot_a_dev", "bot_a_iss", "bot_a_area", "bot_a_found", "bot_a_price", "bot_a_time", "bot_a_contact", "bot_a_hours", "bot_a_human", "bot_a_menu", "bot_a_fallback"] }] },
    slider: { title: "Book-your-slot slider", about: "The slider with one slide per device type and a quick phone / email form that starts the booking on WhatsApp. Opens as the welcome pop-up when chosen, or after the visitor sits idle.", legend: ["site", "slide", "contact"],
        groups: [{ title: "Slides", fields: ["eng_eyebrow", "eng_title2", "eng_perks", "eng_from_label", "eng_slide_ms"] },
            { title: "Form", fields: ["eng_form_pill", "eng_form_title", "eng_form_subtitle", "eng_form_send", "eng_wa_msg", "eng_form_privacy", "eng_form_all", "eng_form_all_link", "eng_form_features"] },
            { title: "When it opens", fields: ["eng_idle_s"] }] },
    exit: { title: "Leaving panel", about: "The panel that slides in from the left when the cursor heads for the browser's top bar or sits still: one tile per device type, each opening WhatsApp.", legend: ["site", "device"],
        groups: [{ title: "Wording", fields: ["exit_title", "exit_status", "exit_text", "exit_button", "exit_wa_msg", "exit_tile_msg", "exit_link_label", "exit_link"] }, { title: "When it opens", fields: ["eng_still_s"] }] },
    cookie: { title: "Cookie notice", about: "The small card at the bottom left on the first visit. The choice is remembered on that browser.",
        groups: [{ title: "The notice", fields: ["cookie_show", "cookie_title", "cookie_text", "cookie_decline", "cookie_accept", "cookie_delay_ms"] }] },
};
// the eight parts of the Pop-ups & chat page, in the order they appear on the screen
const POPUP_PARTS = [["ann", "Announcement bar", "fa-bullhorn"], ["welcome", "Welcome pop-up", "fa-hand-o-right"], ["flash", "Flash offer", "fa-bolt"], ["wheel", "Spin & Win", "fa-gift"],
    ["bot", "Chat assistant", "fa-comments-o"], ["slider", "Book-your-slot slider", "fa-calendar-check-o"], ["exit", "Leaving panel", "fa-sign-out"], ["cookie", "Cookie notice", "fa-circle-o"]];
const ITEM_LIST_OF = { wheel: "wheel", bot: "reply", slider: "slide", exit: "tile" };   // which item list each part edits
const LINE_COLS = {
    hero: ["value", "name"], modes: ["name", "extra", "value", "text"], reviews: ["name", "value", "extra", "stars", "text"],
    milestones: ["value", "name", "text"], partners: ["name", "link"], cta: ["name"],
};
const LINE_TITLE = { hero: "Counters", modes: "The two steps of the flow", reviews: "Reviews", milestones: "Milestones", partners: "Partner logos", cta: "Trust points" };
const INFO_COLUMNS = [["company", "Company"], ["help", "Help"], ["policies", "Policies"], ["none", "Not in the footer"]];
const INFO_KINDS = [["text", "Text page"], ["contact", "Contact (fills itself)"], ["areas", "Areas we cover (fills itself)"], ["faq", "FAQ (fills itself)"]];

export class FixSiteEditor extends Component {
    static template = "369ai_fix.SiteEditor";
    static components = { Layout };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        // green pop-ups (app/screen/fix_popup.js), not Odoo dialogs
        this.popup = useService("fix_popup");
        const ctx = this.props.action?.context || {};
        this.page = ctx.fix_editor_page || "home";
        Object.assign(this, { M, SECTION_FORM, SITE_FORM, LINE_COLS, LINE_TITLE, INFO_COLUMNS, INFO_KINDS, BRAND_FILTERS, PHOTO_FILTERS,
            WELCOME_TYPES, ITEM_KINDS, ICONS, INTENTS, POPUP_PARTS, ITEM_LIST_OF, LEGEND });
        this.state = useState({
            loading: true, d: null, siteId: ctx.fix_site_id || false, pageId: ctx.fix_page_id || false,
            sel: null, status: "saved", screen: "desktop", showHidden: false, showPickup: false,
            infoId: false, zoneTab: 0, newArea: {}, hover: "", mbQuery: "", mbResults: [], mbSearching: false,
            pics: [], filter: "all", q: "",
        });
        this.save = useSaveQueue({
            orm: this.orm, notification: this.notification,
            reload: () => this.load(),
            onStatus: (s) => (this.state.status = s),
            find: (model, id) => this.find(model, id),
        });
        this.canvasRef = useRef("canvas");
        this.rowsRef = useRef("rows");
        useSortable({
            ref: this.canvasRef, elements: ".fx-band[data-band]", handle: ".fx-grip", cursor: "grabbing",
            enable: () => Boolean(this.canvasRef.el) && this.page === "home",
            onDrop: (p) => this.onDrop("sections", p),
        });
        useSortable({
            ref: this.rowsRef, elements: ".fx-row[data-row]", handle: ".fx-grip", cursor: "grabbing",
            enable: () => Boolean(this.rowsRef.el),
            onDrop: (p) => this.onDrop("rows", p),
        });
        // hovering a field: the part of the page it changes lights up and comes into view
        useEffect(() => {
            const key = this.state.hover;
            const el = key && this.canvasRef.el?.querySelector(`[data-fx="${CSS.escape(key)}"]`);
            if (el) {
                el.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
            }
        }, () => [this.state.hover]);
        onWillStart(() => this.load());
    }

    // ------------------------------------------------------------------ data
    async load() {
        const d = await this.orm.call(SITE, "fix_editor_load", [], { site_id: this.state.siteId || false, page_id: this.state.pageId || false });
        if (this.page === "brands" || this.page === "photos") {
            this.state.pics = await this.orm.call(SITE, "fix_editor_pictures", [this.page]);
        }
        if (d.site) {
            d.site.id = d.site_id;
        }
        this.state.siteId = d.site_id;
        this.state.pageId = d.home?.page_id || false;
        this.state.d = d;
        this.state.loading = false;
        if (this.page === "pages" && !(d.pages || []).some((p) => p.id === this.state.infoId)) {
            this.state.infoId = d.pages?.[0]?.id || false;
        }
        if (this.state.sel && !this.selected) {
            this.state.sel = null;
        }
        if (this.page === "pages" && !this.state.sel) {
            this.state.sel = { kind: "pagelist", id: false };
        }
        this.save.applyPending();
    }
    get d() {
        return this.state.d;
    }
    get site() {
        return this.d?.site;
    }
    find(model, id) {
        const d = this.d;
        if (!d) {
            return null;
        }
        if (model === SITE) {
            return d.site;
        }
        const lists = {
            [M.section]: d.home.sections, [M.line]: d.home.sections.flatMap((s) => s.lines).concat(d.flow ? d.flow.lines : []),
            [M.link]: d.links, [M.branch]: d.branches, [M.zone]: d.zones, [M.area]: d.zones.flatMap((z) => z.areas),
            [M.faq]: d.faqs, [M.info]: d.pages, [M.page]: d.home.pages, [M.cat]: d.tiles, [M.item]: d.items || [],
            [M.product]: this.page === "photos" ? this.state.pics : d.most_booked, [M.brand]: this.state.pics,
        };
        return (lists[model] || []).find((r) => r.id === id) || null;
    }

    // --------------------------------------------- brand logos & service pictures
    get picsFiltered() {
        const q = this.state.q.trim().toLowerCase(), f = this.state.filter;
        return this.state.pics.filter((r) => {
            if (q && !`${r.name} ${r.caption || ""} ${r.device || ""} ${r.model || ""}`.toLowerCase().includes(q)) {
                return false;
            }
            if (this.page === "brands") {
                return f === "nologo" ? !r.logo : f === "strip" ? r.in_strip : f === "nostrip" ? !r.in_strip : true;
            }
            return f === "nophoto" ? !r.photos.length : f === "few" ? r.photos.length < 3 : f === "mb" ? r.most_booked : true;
        });
    }
    get picsCounts() {
        const p = this.state.pics;
        return this.page === "brands"
            ? { total: p.length, a: p.filter((b) => b.logo).length, aLabel: "with a logo", b: p.filter((b) => b.in_strip).length, bLabel: "in the strip" }
            : { total: p.length, a: p.filter((s) => s.photos.length).length, aLabel: "with photos", b: p.filter((s) => s.most_booked).length, bLabel: "most booked" };
    }
    get selPic() {
        const s = this.state.sel;
        return s && (s.kind === "brand" || s.kind === "service") ? this.state.pics.find((r) => r.id === s.id) || null : null;
    }
    get stripBrands() {
        return this.state.pics.filter((b) => b.in_strip);
    }
    async uploadLogo(brand, ev) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        const data = await getDataURLFromFile(file);
        await this.save.run(() => this.orm.write(M.brand, [brand.id], { web_logo: data.split(",")[1] }));
    }
    clearLogo(brand) {
        this.save.run(() => this.orm.write(M.brand, [brand.id], { web_logo: false }));
    }
    async uploadPhotos(service, ev) {
        const files = [...(ev.target.files || [])];
        ev.target.value = "";
        if (!files.length) {
            return;
        }
        const vals = [];
        for (const [i, file] of files.entries()) {
            const data = await getDataURLFromFile(file);
            vals.push({ name: file.name.replace(/\.[^.]+$/, ""), product_tmpl_id: service.id, image_1920: data.split(",")[1],
                is_shown: !service.photos.length && i === 0, sequence: (service.photos.length + i + 1) * 10 });
        }
        await this.save.run(() => this.orm.create("fix.web.image", vals), { successMessage: _t("%s photo(s) added", vals.length) });
    }
    showPhoto(photo) {
        this.save.run(() => this.orm.write("fix.web.image", [photo.id], { is_shown: true }));
    }
    removePhoto(service, photo) {
        this.remove("fix.web.image", photo, photo.name);
    }

    // ------------------------------------------------------------ selection
    select(kind, id = false, ev) {
        if (ev && ev.target.closest(".fx-tool, .fx-grip")) {
            return;
        }
        this.state.sel = { kind, id };
        if (kind === "page") {
            this.state.infoId = id;
        }
    }
    /** Every part of the current page, in page order, for the panel's "Editing: …" switcher. */
    get parts() {
        const d = this.d;
        if (!d) {
            return [];
        }
        const header = { v: "header", name: "Header" }, footer = { v: "footer", name: "Footer and contact details" };
        if (this.page === "home") {
            return [header, ...d.home.sections.map((s) => ({ v: `section:${s.id}`, name: s.name + (s.active ? "" : " (hidden)") })), footer];
        }
        if (this.page === "services") {
            return [header, { v: "svc_head", name: "Page heading" }, { v: "flow", name: "Step 1 · How we fix it" },
                { v: "coverage", name: "Step 2 · Coverage areas" }, { v: "faq", name: "FAQ" }, footer];
        }
        if (this.page === "brands") {
            return this.picsFiltered.map((b) => ({ v: `brand:${b.id}`, name: b.name + (b.logo ? "" : " (no logo)") }));
        }
        if (this.page === "photos") {
            return this.picsFiltered.map((s) => ({ v: `service:${s.id}`, name: `${s.name} · ${s.device}` + (s.photos.length ? "" : " (no photo)") }));
        }
        if (this.page === "popups") {
            return POPUP_PARTS.map(([v, name]) => ({ v, name }));
        }
        return [header, ...(this.infoPage ? [{ v: `page:${this.infoPage.id}`, name: "Page · " + this.infoPage.name }] : []), footer];
    }
    get backLabel() {
        return { pages: "All pages", brands: "All brands", photos: "All services", popups: "All pop-ups" }[this.page] || "All sections";
    }
    get curPart() {
        const s = this.state.sel;
        return s ? (s.id ? `${s.kind}:${s.id}` : s.kind) : "";
    }
    /** Switch the panel to another part and bring that part of the page into view. */
    jumpTo(value) {
        const [kind, id] = value.split(":");
        this.select(kind, id ? parseInt(id, 10) : false);
        const canvas = this.canvasRef.el;
        const band = canvas && (canvas.querySelector(`[data-band="${id}"]`) || canvas.querySelector(`.fx-band[data-kind="${kind}"]`)
            || canvas.querySelector(`[data-fx="${CSS.escape(value)}"]`));
        if (band) {
            band.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
        }
        const panel = document.querySelector(".o_fx .fx-panel");
        if (panel) {
            panel.scrollTo({ top: 0 });
        }
    }
    stepPart(delta) {
        const parts = this.parts;
        const i = parts.findIndex((p) => p.v === this.curPart);
        const next = parts[(i + delta + parts.length) % parts.length];
        if (next) {
            this.jumpTo(next.v);
        }
    }
    back() {
        this.state.sel = this.page === "pages" ? { kind: "pagelist", id: false } : null;
        const panel = document.querySelector(".o_fx .fx-panel");
        if (panel) {
            panel.scrollTo({ top: 0 });
        }
    }
    isSel(kind, id = false) {
        const s = this.state.sel;
        return !!s && s.kind === kind && s.id === id;
    }
    get selected() {
        const s = this.state.sel;
        if (!s) {
            return null;
        }
        if (s.kind === "section") {
            return this.find(M.section, s.id);
        }
        if (s.kind === "page") {
            return this.find(M.info, s.id);
        }
        return s;
    }
    get selSection() {
        return this.state.sel?.kind === "section" ? this.find(M.section, this.state.sel.id) : null;
    }
    get infoPage() {
        return (this.d?.pages || []).find((p) => p.id === this.state.infoId) || null;
    }

    // ------------------------------------------------------ fields & highlight
    /** What a field is, for the panel: label, hint, type. "sec.hero.title" falls back to "sec.*.title". */
    help(hk) {
        const parts = hk.split(".");
        const star = parts.length === 3 ? `${parts[0]}.*.${parts[2]}` : hk;
        const h = FIELD_HELP[hk] || FIELD_HELP[star] || {};
        const name = parts[parts.length - 1];
        const type = h.type || (/_(ms|s|days)$/.test(name) ? "int" : "text");
        return { label: h.label || name, hint: h.hint || "", type, now: !!h.now, example: ((h.hint || "").match(/e\.g\. (.*)$/) || [])[1] || "",
            options: h.options || [], on: h.on || "On", off: h.off || "Off" };
    }
    /** A highlight key: K('sec', 12, 'title') -> "sec:12:title" */
    K(...parts) {
        return parts.join(":");
    }
    hl(key) {
        return this.state.hover === key ? " fx-hl" : "";
    }
    onPanelOver(ev) {
        const el = ev.target.closest("[data-fx-for]");
        this.state.hover = el ? el.dataset.fxFor : "";
    }

    // --------------------------------------------------------------- edits
    edit(model, rec, field, ev, opts) {
        this.save.edit(model, rec, field, this.save.valueFrom(ev), opts);
    }
    toggle(model, rec, field = "active", as = null) {
        this.save.edit(model, rec, field, !rec[field], { now: true, as });
    }
    async add(model, vals, { select } = {}) {
        const [id] = await this.save.run(() => this.orm.create(model, [vals]));
        if (select) {
            this.select(select, id);
        }
        return id;
    }
    async remove(model, rec, what) {
        const sure = await this.popup.confirm(
            _t("Remove %s from the website? This cannot be undone. (To hide it instead, press the eye.)", what || rec.name || ""),
            { danger: true, ok: _t("Remove"), cancel: _t("Keep it") });
        if (!sure) {
            return;
        }
        await this.save.run(() => this.orm.unlink(model, [rec.id]));
        if (this.state.sel && this.state.sel.id === rec.id) {
            this.state.sel = null;
        }
    }
    async upload(model, rec, ev) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        const data = await getDataURLFromFile(file);
        await this.save.run(() => this.orm.write(model, [rec.id], { image_1920: data.split(",")[1] }));
    }
    clearImage(model, rec) {
        this.save.run(() => this.orm.write(model, [rec.id], { image_1920: false }));
    }

    // -------------------------------------------------------------- reorder
    async onDrop(which, { element, previous, next }) {
        let model = null, list = null, field = "sequence";
        if (which === "sections") {
            model = M.section;
            list = this.d.home.sections;
        } else {
            const s = this.state.sel;
            if (!s) {
                return;
            }
            const sec = s.kind === "section" ? this.find(M.section, s.id) : null;
            if (sec && sec.kind === "services") {
                model = M.product; list = this.d.most_booked; field = "web_home_sequence";
            } else if (sec) {
                model = M.line; list = sec.lines;
            } else if (s.kind === "flow") {
                model = M.line; list = this.d.flow?.lines;
            } else if (s.kind === "faq") {
                model = M.faq; list = this.d.faqs;
            } else if (s.kind === "header" || s.kind === "footer") {
                model = M.link; list = this.d.links;
            } else if (s.kind === "pagelist") {
                model = M.info; list = this.d.pages;
            } else if (s.kind === "coverage") {
                model = M.zone; list = this.d.zones;
            } else if (ITEM_LIST_OF[s.kind]) {
                model = M.item; list = this.items(ITEM_LIST_OF[s.kind]);
            }
        }
        if (!list) {
            return;
        }
        const idOf = (el) => parseInt(el.dataset.band || el.dataset.row, 10);
        const from = list.findIndex((r) => r.id === idOf(element));
        if (from < 0) {
            return;
        }
        const before = [...list];
        const [row] = list.splice(from, 1);
        let to = 0;
        if (previous) {
            to = list.findIndex((r) => r.id === idOf(previous)) + 1;
        } else if (next) {
            to = Math.max(0, list.findIndex((r) => r.id === idOf(next)));
        }
        list.splice(to, 0, row);
        try {
            await this.orm.call(model, "web_resequence", [list.map((r) => r.id), {}], { field_name: field });
            await this.load();
        } catch {
            list.splice(0, list.length, ...before);
            this.notification.add(_t("That order did not save."), { type: "danger" });
        }
    }

    // ------------------------------------------------------- lines & lists
    linesOf(section) {
        return (section.lines || []).filter((l) => l.role !== "popular");
    }
    popularOf(section) {
        return (section.lines || []).filter((l) => l.role === "popular");
    }
    addLine(section) {
        return this.add(M.line, { section_id: section.id, name: _t("New line"), stars: 5 });
    }
    addPopular(section) {
        return this.add(M.line, { section_id: section.id, role: "popular", name: _t("New link"), link: "/services#catalog", sequence: 100 + this.popularOf(section).length * 10 });
    }
    addLink(kind) {
        return this.add(M.link, { site_id: this.d.site_id, kind, name: _t("New link"), link: "/" });
    }
    addBranch() {
        return this.add(M.branch, { site_id: this.d.site_id, name: _t("New branch") });
    }
    addFaq() {
        return this.add(M.faq, { site_id: this.d.site_id, name: _t("New question?"), answer: _t("The answer.") });
    }
    addZone(mode) {
        return this.add(M.zone, { site_id: this.d.site_id, mode, name: _t("New zone") });
    }
    async addArea(zone) {
        const name = (this.state.newArea[zone.id] || "").trim();
        if (!name) {
            return;
        }
        this.state.newArea[zone.id] = "";
        await this.add(M.area, { zone_id: zone.id, name, sequence: (zone.areas.length + 1) * 10 });
    }
    onAreaKey(zone, ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.addArea(zone);
        }
    }
    async addInfoPage() {
        const id = await this.add(M.info, { site_id: this.d.site_id, name: _t("New page"), slug: `page-${Date.now() % 100000}`, column: "company", kind: "text" });
        this.select("page", id);
    }
    addSection(kind) {
        return this.add(M.section, { page_id: this.state.pageId, kind, sequence: (this.d.home.sections.length + 1) * 10 }, { select: "section" });
    }
    get missingKinds() {
        const have = new Set((this.d?.home.sections || []).map((s) => s.kind));
        return (this.d?.home.kinds || []).filter((k) => !have.has(k.key));
    }

    // ------------------------------------------------------------ pop-ups & chat
    /** The rows of one list: wheel (prizes), reply (chat chips), slide, tile. In order, hidden ones too. */
    items(kind) {
        return (this.d?.items || []).filter((i) => i.kind === kind);
    }
    activeItems(kind) {
        return this.items(kind).filter((i) => i.active);
    }
    addItem(kind) {
        const seq = (this.items(kind).length + 1) * 10;
        const firstCat = (this.d?.tiles || [])[0];
        const vals = {
            wheel: { name2: _t("Free"), name: _t("Prize"), text: _t("A free extra"), code: `SPIN-${Date.now() % 1000}`, icon: "diag", color: "#f5b400", color2: "#10241a" },
            reply: { name: _t("New chip"), code: "menu" },
            slide: { name: firstCat ? firstCat.name : _t("Device"), name2: _t("Repair"), text: "", text2: "", category_id: firstCat ? firstCat.id : false },
            tile: { name: "", category_id: firstCat ? firstCat.id : false },
        }[kind];
        return this.add(M.item, { site_id: this.d.site_id, kind, sequence: seq, ...vals });
    }
    /** A select or a colour of a list row: saved at once, so the preview follows. */
    editItem(it, field, value) {
        this.save.edit(M.item, it, field, value, { now: true });
    }
    editItemCategory(it, ev) {
        this.editItem(it, "category_id", parseInt(ev.target.value, 10) || false);
    }
    catName(id) {
        return ((this.d?.tiles || []).find((c) => c.id === id) || {}).name || "";
    }
    tileLabel(it) {
        return it.name || this.catName(it.category_id);
    }
    /** The wheel as the site draws it: one conic-gradient slice per active prize, from 12 o'clock clockwise. */
    wheelGradient() {
        const s = this.activeItems("wheel");
        if (!s.length) {
            return "conic-gradient(#d6dbd7 0deg 360deg)";
        }
        const seg = 360 / s.length;
        return "conic-gradient(" + s.map((x, i) => `${x.color || "#ccc"} ${(i * seg).toFixed(2)}deg ${((i + 1) * seg).toFixed(2)}deg`).join(", ") + ")";
    }
    sliceStyle(i, n, slice) {
        return `transform: rotate(${((i + 0.5) * 360 / n).toFixed(2)}deg); color: ${slice.color2 || "#fff"}`;
    }
    get welcomeChoice() {
        return WELCOME_TYPES.find((w) => w[0] === (this.site?.welcome_popup || "slot")) || WELCOME_TYPES[0];
    }
    /** "Quick Service|In most areas" lines → [{title, small}] */
    features() {
        return this.lines(this.site?.eng_form_features).map((x) => {
            const [title, small] = x.split("|");
            return { title: (title || "").trim(), small: (small || "").trim() };
        });
    }
    get firstSlide() {
        return this.activeItems("slide")[0] || null;
    }
    legendText(keys) {
        return (keys || []).map((k) => `{${k}} = ${LEGEND[k] || k}`).join(" · ");
    }

    // --------------------------------------------- device tiles & most booked
    toggleTile(tile) {
        this.save.edit(M.cat, tile, "show", !tile.show, { now: true, as: "web_show_home" });
    }
    removeMostBooked(p) {
        this.save.run(() => this.orm.write(M.product, [p.id], { web_most_booked: false }));
    }
    async searchServices(ev) {
        const q = ev.target.value;
        this.state.mbQuery = q;
        if (q.trim().length < 2) {
            this.state.mbResults = [];
            return;
        }
        this.state.mbSearching = true;
        const res = await this.orm.call(SITE, "fix_editor_search_services", [q]);
        if (this.state.mbQuery === q) {
            this.state.mbResults = res;
            this.state.mbSearching = false;
        }
    }
    async pickService(r) {
        const seq = Math.max(0, ...this.d.most_booked.map((p) => p.sequence || 0)) + 10;
        this.state.mbQuery = "";
        this.state.mbResults = [];
        await this.save.run(() => this.orm.write(M.product, [r.id], { web_most_booked: true, web_home_sequence: seq }));
    }

    // ---------------------------------------------------- pages & settings
    async switchHomePage(id) {
        await this.save.flushNow().catch(() => {});
        this.state.pageId = id;
        this.state.sel = null;
        await this.load();
    }
    openHomePageForm() {
        this.popup.doAction({
            type: "ir.actions.act_window", res_model: M.page, res_id: this.state.pageId, views: [[this.d.views.home_page, "form"]], target: "new",
        }, { onClose: () => this.load() });
    }
    writePageText(page) {
        this.popup.doAction({
            type: "ir.actions.act_window", res_model: M.info, res_id: page.id, views: [[this.d.views.page_text, "form"]], target: "new",
        }, { onClose: () => this.load() });
    }
    openWebsite(path = "/") {
        const base = (this.site?.public_url || "").replace(/\/$/, "");
        window.open(base + path, "_blank", "noopener");
    }
    async switchSite(ev) {
        await this.save.flushNow().catch(() => {});
        this.state.siteId = parseInt(ev.target.value, 10);
        this.state.pageId = false;
        this.state.sel = null;
        await this.load();
    }

    // ------------------------------------------------------------ drawing
    html(s) {
        return markup(s || "");
    }
    lines(text) {
        return String(text || "").split("\n").map((x) => x.trim()).filter(Boolean);
    }
    /** The one repair flow from the two "modes" lines (same rule as the website). */
    get flow() {
        const src = this.page === "home" ? this.d.home.sections.find((s) => s.kind === "modes") : this.d.flow;
        const ls = (src?.lines || []).filter((l) => l.active && l.role !== "popular");
        const v = ls[0] || {}, lab = ls[1] || {};
        const steps = this.lines(v.text);
        return { id1: v.id, id2: lab.id, title: v.name || "", eta: v.value || "", shared: steps.slice(0, -1), spot: steps[steps.length - 1] || "",
            lab: { title: lab.name || "", note: lab.extra || "", eta: lab.value || "", steps: this.lines(lab.text),
                line: [lab.extra, lab.value].filter(Boolean).join(" · ") } };
    }
    get visibleSections() {
        return (this.d?.home.sections || []).filter((s) => s.active || this.state.showHidden);
    }
    get hiddenCount() {
        return (this.d?.home.sections || []).filter((s) => !s.active).length;
    }
    get menuLinks() {
        return (this.d?.links || []).filter((l) => l.kind === "header" && l.active);
    }
    get quickLinks() {
        return (this.d?.links || []).filter((l) => l.kind === "quick" && l.active);
    }
    get footerColumns() {
        // as the website: a text page without text is not shown yet
        return [["company", "Company"], ["help", "Help"], ["policies", "Policies"]]
            .map(([key, label]) => ({ key, label, pages: (this.d?.pages || []).filter((p) => p.active && p.column === key && (p.kind !== "text" || p.body)) }))
            .filter((c) => c.pages.length);
    }
    get doorstepZones() {
        return (this.d?.zones || []).filter((z) => z.mode === "doorstep" && z.active);
    }
    get zoneShown() {
        const zs = this.doorstepZones;
        return zs[Math.min(this.state.zoneTab, Math.max(0, zs.length - 1))] || null;
    }
    mapSrc(zone) {
        const pin = zone && (zone.latitude || zone.longitude) ? [zone.latitude, zone.longitude]
            : (zone?.areas || []).map((a) => (a.latitude || a.longitude) ? [a.latitude, a.longitude] : null).find(Boolean);
        if (!pin) {
            return "";
        }
        const [lat, lng] = pin;
        return `https://www.openstreetmap.org/export/embed.html?bbox=${lng - 0.09}%2C${lat - 0.06}%2C${lng + 0.09}%2C${lat + 0.06}&layer=mapnik&marker=${lat}%2C${lng}`;
    }
    /** What the website puts in place of the words in curly brackets, for the preview. */
    fill(text) {
        const d = this.d || {}, site = this.site || {}, flow = this.flow;
        const fee = d.visit_fee ? `Visit fee OMR ${d.visit_fee}` : "Visit fee: price after check";
        const map = {
            price: d.price || "", site: site.name || "", code: site.flash_code || "", fee, hours: d.hours || "", device: "Laptop",
            issue: "Screen replacement", area: "Qurum", branches: (d.branches || []).filter((b) => b.active).map((b) => b.name).join(", "),
            phone: site.contact_phone || "", email: site.contact_email || "", doorstep: flow.eta || "", pickup: flow.lab.eta || "",
            slide: "Mobile Repair", contact: "+968 9123 4567",
        };
        return String(text || "").replace(/\{(\w+)\}/g, (m, k) => (k in map ? map[k] : m));
    }
    stars(n) {
        const k = Math.max(0, Math.min(5, parseInt(n, 10) || 0));
        return "★".repeat(k) + "☆".repeat(5 - k);
    }
    branchLines(b) {
        return this.lines(b.address);
    }
    phones(b) {
        return String(b.phones || "").split(",").map((x) => x.trim()).filter(Boolean);
    }
    pageLabel(kind) {
        return (INFO_KINDS.find(([k]) => k === kind) || [])[1] || kind;
    }
    get siteHost() {
        return (this.site?.public_url || "danatfix.com").replace(/^https?:\/\//, "");
    }
    isTbc(v) {
        return /tbc/i.test(v || "");
    }
    zoneLabel(z) {
        return (z.name || "").replace(/ \(.*\)/, "");
    }
    zoneBranch(z) {
        const m = (z.name || "").match(/\((.*)\)/);
        return m ? m[1] : "";
    }
    singular(s) {
        return String(s || "").replace(/s$/, "");
    }
    year() {
        return new Date().getFullYear();
    }
    get statusText() {
        return { saving: _t("Saving…"), saved: _t("Saved"), error: _t("Not saved") }[this.state.status] || "";
    }
}

registry.category("actions").add("369ai_fix.site_editor", FixSiteEditor);
