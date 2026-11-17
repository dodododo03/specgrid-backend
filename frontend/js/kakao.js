// Kakao Maps: lazy SDK loader + "open in Kakao Map" links.
//
// The JavaScript key comes from the server (/client-config, set via KAKAO_JS_KEY in .env), so it is
// not hard-coded here. It is public by design: Kakao only accepts it from the domains registered in
// Kakao Developers. If there is no key, or the SDK can't load (offline, unregistered domain), the map
// just isn't shown — the directions link below works without the SDK.

import * as api from "./api.js";

let sdk = null;

/** Resolves to window.kakao with maps + services ready, or rejects if maps are unavailable. */
export function loadKakaoMaps() {
  if (!sdk) {
    sdk = (async () => {
      const { kakao_js_key: key } = await api.get("/client-config", null, { auth: "none" });
      if (!key) throw new Error("카카오맵 키가 설정되지 않았어요.");
      if (!window.kakao?.maps) {
        await new Promise((resolve, reject) => {
          const s = document.createElement("script");
          s.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(key)}&libraries=services&autoload=false`;
          s.onload = resolve;
          s.onerror = () => reject(new Error("카카오맵을 불러오지 못했어요."));
          document.head.append(s);
        });
      }
      // An unregistered domain still "loads" the script but never defines kakao.maps.
      if (!window.kakao?.maps?.load) throw new Error("카카오맵을 사용할 수 없어요. (도메인 등록 확인)");
      await new Promise((resolve) => window.kakao.maps.load(resolve));
      return window.kakao;
    })();
    sdk.catch(() => (sdk = null)); // allow a retry on the next page
  }
  return sdk;
}

// Kakao's link format is name,lat,lng — a comma inside the name would break it.
const linkName = (name) => encodeURIComponent((name || "거래 장소").replace(/,/g, " "));

/** Kakao Map with this place as the destination (car / transit / walk / bike chosen there). */
export function directionsUrl(name, { lat, lng }) {
  return `https://map.kakao.com/link/to/${linkName(name)},${lat},${lng}`;
}

/** Kakao Map centred on this place. */
export function placeUrl(name, { lat, lng }) {
  return `https://map.kakao.com/link/map/${linkName(name)},${lat},${lng}`;
}

/** Draw a map with one marker. Returns { map, marker } for further use. */
export function drawMap(kakao, container, { lat, lng }, { level = 3, draggable = true } = {}) {
  const center = new kakao.maps.LatLng(lat, lng);
  const map = new kakao.maps.Map(container, { center, level, draggable, scrollwheel: false });
  map.addControl(new kakao.maps.ZoomControl(), kakao.maps.ControlPosition.RIGHT);
  const marker = new kakao.maps.Marker({ position: center, map });
  return { map, marker };
}
