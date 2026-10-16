/** @odoo-module **/

/**
 * The live map of the Booking Desk, on Leaflet 1.9.4 (static/lib/leaflet, loaded
 * before this file; it puts `L` on window). OpenStreetMap tiles. No marker images:
 * the customer is a green pin (divIcon), the technician a blue dot (circleMarker),
 * the trail a grey line, so nothing has to be downloaded besides the tiles.
 *
 *   const map = mountMap(el);     // once, on a visible element with a height
 *   updateMap(map, data);         // data = detail.map from fix_desk_detail()
 *   destroyMap(map);              // when the element goes away
 */

const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors';
const CUSTOMER_ICON_HTML =
    '<span class="fxd-pin"><i class="fa fa-home"></i></span>';

function leaflet() {
    return window.L || null;
}

export function hasLeaflet() {
    return !!leaflet();
}

export function mountMap(el) {
    const L = leaflet();
    if (!L || !el) {
        return null;
    }
    const map = L.map(el, { zoomControl: true, attributionControl: true, tap: false });
    L.tileLayer(TILES, { maxZoom: 19, attribution: ATTRIBUTION }).addTo(map);
    map.setView([23.588, 58.38], 11);
    return {
        map,
        customer: null,
        tech: null,
        trail: null,
        start: null,
        fitted: "",
    };
}

function sameKey(data) {
    const c = data.customer ? `${data.customer.lat},${data.customer.lng}` : "";
    const t = data.tech ? `${data.tech.lat},${data.tech.lng}` : "";
    return `${c}|${t}`;
}

/** Draw `data` ({customer, tech, trail, start, live}); fits the view when the points changed. */
export function updateMap(handle, data) {
    const L = leaflet();
    if (!handle || !L) {
        return;
    }
    const { map } = handle;
    const points = [];

    // customer
    if (data && data.customer) {
        const latlng = [data.customer.lat, data.customer.lng];
        if (!handle.customer) {
            handle.customer = L.marker(latlng, {
                icon: L.divIcon({ className: "fxd-pin-wrap", html: CUSTOMER_ICON_HTML, iconSize: [34, 42], iconAnchor: [17, 40] }),
                keyboard: false,
            }).addTo(map);
        } else {
            handle.customer.setLatLng(latlng);
        }
        points.push(latlng);
    } else if (handle.customer) {
        handle.customer.remove();
        handle.customer = null;
    }

    // trail (oldest first) and where the technician set off
    const trail = (data && data.trail) || [];
    if (trail.length > 1) {
        if (!handle.trail) {
            handle.trail = L.polyline(trail, { color: "#7a8a80", weight: 4, opacity: 0.8, dashArray: "2 8", lineCap: "round" }).addTo(map);
        } else {
            handle.trail.setLatLngs(trail);
        }
    } else if (handle.trail) {
        handle.trail.remove();
        handle.trail = null;
    }
    if (data && data.start && data.live) {
        const latlng = [data.start.lat, data.start.lng];
        if (!handle.start) {
            handle.start = L.circleMarker(latlng, { radius: 5, color: "#7a8a80", weight: 2, fillColor: "#fff", fillOpacity: 1 }).addTo(map);
        } else {
            handle.start.setLatLng(latlng);
        }
    } else if (handle.start) {
        handle.start.remove();
        handle.start = null;
    }

    // technician
    if (data && data.tech) {
        const latlng = [data.tech.lat, data.tech.lng];
        const color = data.tech.stale ? "#9aa5a0" : "#1f6fd1";
        if (!handle.tech) {
            handle.tech = L.circleMarker(latlng, { radius: 9, color: "#fff", weight: 3, fillColor: color, fillOpacity: 1, className: "fxd-dot" }).addTo(map);
        } else {
            handle.tech.setLatLng(latlng);
            handle.tech.setStyle({ fillColor: color });
        }
        points.push(latlng);
    } else if (handle.tech) {
        handle.tech.remove();
        handle.tech = null;
    }

    // the view: fit both points the first time they appear, follow the technician after that
    const key = sameKey(data || {});
    if (points.length && key !== handle.fitted) {
        const both = points.length > 1;
        if (both && !handle.fitted.split("|")[1]) {
            map.fitBounds(L.latLngBounds(points), { padding: [36, 36], maxZoom: 16 });
        } else if (!handle.fitted) {
            map.setView(points[0], 15);
        } else if (data.tech) {
            if (!map.getBounds().pad(-0.2).contains(points[points.length - 1])) {
                map.panTo(points[points.length - 1]);
            }
        }
        handle.fitted = key;
    }
    setTimeout(() => map.invalidateSize(), 50);
}

export function destroyMap(handle) {
    if (handle && handle.map) {
        handle.map.remove();
    }
}
