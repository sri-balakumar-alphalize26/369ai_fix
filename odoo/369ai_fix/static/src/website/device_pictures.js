/** @odoo-module */

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// Fix Website > Pictures > Device Pictures: one switch, Sketch Drawing | Real Photos.
// Drawing: pick the style every device type uses. Photos: tap the photo each device type uses.
// Every choice is saved straight away (onSelect); the website follows within 5 minutes.
class FixDevicePictures extends Component {
    static template = "369ai_fix.DevicePictures";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.popup = useService("fix_popup");
        this.notification = useService("notification");
        this.state = useState({
            loading: true, sites: [], siteId: false, mode: "drawing", style: "3d",
            styles: [], devices: [], viewId: false,
        });
        onWillStart(() => this.load());
    }

    async load(siteId) {
        const data = await this.orm.call("online.service.site", "fix_device_pictures_data", [], {
            site_id: siteId || this.state.siteId || false,
        });
        Object.assign(this.state, {
            sites: data.sites, siteId: data.site_id, mode: data.mode, style: data.style,
            styles: data.styles, devices: data.devices, viewId: data.device_form_view_id, loading: false,
        });
    }

    /** The selection callback: {mode}, {style} or {device_id, photo_id}. Saved at once, undone if saving fails. */
    async onSelect(selection) {
        const before = { mode: this.state.mode, style: this.state.style,
                         shown: this.state.devices.map((d) => d.photos.map((p) => p.shown)) };
        if (selection.mode) this.state.mode = selection.mode;
        if (selection.style) this.state.style = selection.style;
        if (selection.photo_id) {
            const device = this.state.devices.find((d) => d.id === selection.device_id);
            device.photos.forEach((p) => (p.shown = p.id === selection.photo_id));
        }
        try {
            await this.orm.call("online.service.site", "fix_device_pictures_save", [this.state.siteId, selection]);
            this.notification.add("Saved. The website shows it within 5 minutes.", { type: "success" });
        } catch (error) {
            this.state.mode = before.mode;
            this.state.style = before.style;
            this.state.devices.forEach((d, i) => d.photos.forEach((p, j) => (p.shown = before.shown[i][j])));
            this.notification.add(error.data?.message || error.message || "Could not save.", { type: "danger" });
        }
    }

    setMode(mode) {
        if (mode !== this.state.mode) this.onSelect({ mode });
    }

    setStyle(style) {
        if (style !== this.state.style) this.onSelect({ style });
    }

    selectPhoto(device, photo) {
        if (!photo.shown) this.onSelect({ device_id: device.id, photo_id: photo.id });
    }

    changeSite(ev) {
        this.load(parseInt(ev.target.value, 10));
    }

    /** The device type's drawings and photos, on the green Device Categories screen. */
    editDevice(device) {
        this.popup.openScreen({ screen: "categories", id: device.id });
    }
}

registry.category("actions").add("369ai_fix.device_pictures", FixDevicePictures);
