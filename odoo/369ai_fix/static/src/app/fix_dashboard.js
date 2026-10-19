/** @odoo-module */

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// The numbers of the 369 ai Fix flow, in the same look as the Booking Desk
// (fix_dashboard.scss; each tile opens its green screen on the filter that counts it).
class FixDashboard extends Component {
    static template = "369ai_fix.Dashboard";

    setup() {
        this.actionService = useService("action");
        this.popup = useService("fix_popup");
        this.orm = useService("orm");
        this.state = useState({ isLoading: true, data: {}, maxCompleted: 1 });
        onWillStart(() => this.load());
    }

    async load() {
        try {
            const data = await this.orm.call("fix.dashboard", "get_dashboard_data", []);
            this.state.data = data;
            this.state.maxCompleted = Math.max(...(data.completed_by_month || []).map((m) => m.count), 1);
        } catch (error) {
            console.error("369 ai Fix dashboard:", error);
            this.state.data = { state_counts: {}, visits: {}, completed_by_month: [] };
        }
        this.state.isLoading = false;
    }

    /** A tile: the green screen on the filter that gives the tile's number. */
    open(screen, filter) {
        this.popup.openScreen({ screen, filter });
    }

    /** Bar height in % of the tallest month; a month with repairs is never shorter than 5 %. */
    barHeight(item) {
        if (!item.count) {
            return 2;
        }
        return Math.max((item.count / this.state.maxCompleted) * 100, 5);
    }

    openJobCards(state) {
        this.open("job_cards", state);
    }

    openVisits(filter) {
        this.open("visits", filter);
    }
}

registry.category("actions").add("369ai_fix_dashboard", FixDashboard);
