/** @odoo-module */

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// Same look as the IT & Mobile Repair dashboard (it reuses that screen's styles),
// with the numbers of the 369 ai Fix flow only.
class FixDashboard extends Component {
    static template = "369ai_fix.Dashboard";

    setup() {
        this.actionService = useService("action");
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

    open(xmlid) {
        this.actionService.doAction(xmlid);
    }

    openJobCards(state) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Job Cards",
            res_model: "job.card",
            views: [[false, "list"], [false, "form"]],
            domain: [["online_order_id", "!=", false], ["state", "=", state]],
            context: { create: false },
            target: "current",
        });
    }

    openVisits(states) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Doorstep Visits",
            res_model: "fix.service.visit",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "in", states]],
            target: "current",
        });
    }
}

registry.category("actions").add("369ai_fix_dashboard", FixDashboard);
