#!/usr/bin/env node

import { loadEnvFile, CHROME_UA, getRedisCredentials, runSeed } from "./_seed-utils.mjs";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

loadEnvFile(import.meta.url);

const __dirname = dirname(fileURLToPath(import.meta.url));
const CANONICAL_KEY = "conflict:iran-events:v1";

const LOCATION_COORDS = {
	tehran: { lat: 35.6892, lon: 51.389 },
	isfahan: { lat: 32.6546, lon: 51.668 },
	shiraz: { lat: 29.5918, lon: 52.5837 },
	mashhad: { lat: 36.2605, lon: 59.6168 },
	tabriz: { lat: 38.08, lon: 46.2919 },
	ahvaz: { lat: 31.3183, lon: 48.6706 },
	kermanshah: { lat: 34.3142, lon: 47.065 },
	urmia: { lat: 37.5527, lon: 45.0761 },
	bushehr: { lat: 28.9234, lon: 50.8203 },
	"bandar abbas": { lat: 27.1865, lon: 56.2808 },
	erbil: { lat: 36.1912, lon: 44.0119 },
	baghdad: { lat: 33.3152, lon: 44.3661 },
	basra: { lat: 30.5085, lon: 47.7804 },
	mosul: { lat: 36.335, lon: 43.1189 },
	"tel aviv": { lat: 32.0853, lon: 34.7818 },
	israel: { lat: 31.7683, lon: 35.2137 },
	negev: { lat: 30.8, lon: 34.8 },
	manama: { lat: 26.2285, lon: 50.586 },
	bahrain: { lat: 26.0667, lon: 50.5577 },
	kuwait: { lat: 29.3759, lon: 47.9774 },
	dubai: { lat: 25.2048, lon: 55.2708 },
	"abu dhabi": { lat: 24.4539, lon: 54.3773 },
	fujairah: { lat: 25.1288, lon: 56.3265 },
	qatar: { lat: 25.2854, lon: 51.531 },
	doha: { lat: 25.2854, lon: 51.531 },
	jordan: { lat: 31.9454, lon: 35.9284 },
	irbid: { lat: 32.556, lon: 35.85 },
	syria: { lat: 34.8021, lon: 38.9968 },
	daraa: { lat: 32.6189, lon: 36.1021 },
	cyprus: { lat: 34.7071, lon: 33.0226 },
	akrotiri: { lat: 34.5839, lon: 32.9879 },
	hormuz: { lat: 27.0, lon: 56.5 },
	"strait of hormuz": { lat: 26.5, lon: 56.3 },
	parchin: { lat: 35.5167, lon: 51.7667 },
	mehrabad: { lat: 35.6892, lon: 51.3134 },
	paveh: { lat: 35.0442, lon: 46.3558 },
	poldokhtar: { lat: 33.1517, lon: 47.7133 },
	azadi: { lat: 35.6997, lon: 51.338 },
	kohak: { lat: 35.6, lon: 51.5 },
	zibashir: { lat: 29.55, lon: 52.55 },
	jam: { lat: 27.82, lon: 52.35 },
	london: { lat: 51.5074, lon: -0.1278 },
	azerbaijan: { lat: 40.4093, lon: 49.8671 },
	baku: { lat: 40.4093, lon: 49.8671 },
	gibraltar: { lat: 36.1408, lon: -5.3536 },
	iran: { lat: 32.4279, lon: 53.688 },
	iraq: { lat: 33.2232, lon: 43.6793 },
	saudi: { lat: 24.7136, lon: 46.6753 },
	uae: { lat: 24.4539, lon: 54.3773 },
	"al udeid": { lat: 25.1173, lon: 51.315 },
	jomhouri: { lat: 35.685, lon: 51.405 },
	"jurf al-sakhar": { lat: 32.95, lon: 44.1 },
	"haji omeran": { lat: 36.65, lon: 45.05 },
	nineveh: { lat: 36.35, lon: 43.15 },
	rashidiya: { lat: 36.4, lon: 43.1 },
	gaza: { lat: 31.3547, lon: 34.3088 },
	riyadh: { lat: 24.7136, lon: 46.6753 },
	sulaimaniyah: { lat: 35.5613, lon: 45.4306 },
	sulaimani: { lat: 35.5613, lon: 45.4306 },
	haifa: { lat: 32.794, lon: 34.9896 },
	karaj: { lat: 35.84, lon: 50.9391 },
	shahran: { lat: 35.79, lon: 51.29 },
	kouhak: { lat: 35.62, lon: 51.48 },
	hamadan: { lat: 34.7988, lon: 48.5146 },
	hamedan: { lat: 34.7988, lon: 48.5146 },
	yazd: { lat: 31.8974, lon: 54.3569 },
	kish: { lat: 26.54, lon: 53.98 },
	qazvin: { lat: 36.2688, lon: 50.0041 },
	najafabad: { lat: 32.634, lon: 51.367 },
	malayer: { lat: 34.2968, lon: 48.8234 },
	mehran: { lat: 33.1222, lon: 46.1646 },
	aqaba: { lat: 29.5267, lon: 35.0078 },
	eilat: { lat: 29.5577, lon: 34.9519 },
	choman: { lat: 36.6269, lon: 44.8856 },
	"baqer shahr": { lat: 35.54, lon: 51.39 },
	jubail: { lat: 27.0046, lon: 49.6225 },
	shaybah: { lat: 22.52, lon: 54.0 },
	"al dhafra": { lat: 24.25, lon: 54.55 },
	juffair: { lat: 26.2167, lon: 50.6 },
	qeshm: { lat: 26.95, lon: 56.27 },
	pakdasht: { lat: 35.4747, lon: 51.6856 },
	tasluja: { lat: 35.51, lon: 45.37 },
	"al-kharj": { lat: 24.15, lon: 47.31 },
	"petah tikva": { lat: 32.0841, lon: 34.8878 },
	beersheba: { lat: 31.2518, lon: 34.7913 },
	oman: { lat: 23.588, lon: 58.3829 },
	oslo: { lat: 59.9139, lon: 10.7522 },
	norway: { lat: 59.9139, lon: 10.7522 },
	aghdasiyeh: { lat: 35.79, lon: 51.45 },
	rey: { lat: 35.5959, lon: 51.435 },
	beirut: { lat: 33.8938, lon: 35.5018 },
	azraq: { lat: 31.83, lon: 36.83 },
	yehud: { lat: 32.0333, lon: 34.8833 },
	sitra: { lat: 26.1547, lon: 50.6028 },
	sanandaj: { lat: 35.3219, lon: 46.9862 },
	"ma'ameer": { lat: 26.05, lon: 50.52 },
	"northern cyprus": { lat: 35.1856, lon: 33.3823 },
	borujerd: { lat: 33.8973, lon: 48.7516 },
	lamerd: { lat: 27.3373, lon: 53.1831 },
	chabahar: { lat: 25.2919, lon: 60.643 },
	shahrekord: { lat: 32.3256, lon: 50.8644 },
	parand: { lat: 35.487, lon: 51.005 },
	"rabat karim": { lat: 35.47, lon: 51.07 },
	shahriar: { lat: 35.6569, lon: 51.0592 },
	punak: { lat: 35.76, lon: 51.36 },
	bonab: { lat: 37.3404, lon: 46.0561 },
	ghaniabad: { lat: 35.45, lon: 51.65 },
	"beit shemesh": { lat: 31.7469, lon: 34.9876 },
	"bnei brak": { lat: 32.0833, lon: 34.8333 },
	quneitra: { lat: 33.126, lon: 35.824 },
	"khan arnabeh": { lat: 33.145, lon: 35.86 },
	ruwais: { lat: 24.11, lon: 52.73 },
	mehrshahr: { lat: 35.83, lon: 50.97 },
	qaim: { lat: 34.38, lon: 41.04 },
	"prince sultan": { lat: 24.0625, lon: 47.5808 },
	"ramat david": { lat: 32.665, lon: 35.1792 },
	vietnam: { lat: 14.0583, lon: 108.2772 },
	"south korea": { lat: 35.9078, lon: 127.7669 },
	ilam: { lat: 33.6374, lon: 46.4227 },
	kerman: { lat: 30.2839, lon: 57.0834 },
	lorestan: { lat: 33.4941, lon: 48.353 },
	jerusalem: { lat: 31.7683, lon: 35.2137 },
	fardis: { lat: 35.723, lon: 50.9875 },
	marivan: { lat: 35.5269, lon: 46.1761 },
	salalah: { lat: 17.0151, lon: 54.0924 },
	palmachim: { lat: 31.897, lon: 34.7 },
	"umm qasr": { lat: 30.0362, lon: 47.9298 },
	"al-siba": { lat: 29.87, lon: 48.61 },
	taleghan: { lat: 36.17, lon: 50.76 },
	"persian gulf": { lat: 27.0, lon: 51.5 },
	"eastern province": { lat: 26.4207, lon: 50.0888 },
	"empty quarter": { lat: 22.52, lon: 54.0 },
	ovadia: { lat: 31.47, lon: 34.53 },
	"shin bet": { lat: 31.7683, lon: 35.2137 },
	kharg: { lat: 29.2635, lon: 50.3273 },
	qom: { lat: 34.6401, lon: 50.8764 },
	andisheh: { lat: 35.705, lon: 51.0 },
	ankara: { lat: 39.9334, lon: 32.8597 },
	minab: { lat: 27.1452, lon: 57.0812 },
	asaluyeh: { lat: 27.4834, lon: 52.6121 },
	"south pars": { lat: 27.5, lon: 52.5 },
	"al-ahmadi": { lat: 29.0769, lon: 48.0839 },
	"mina al-ahmadi": { lat: 29.0769, lon: 48.0839 },
	"mina abdullah": { lat: 28.96, lon: 48.16 },
	"kafr qasim": { lat: 32.1161, lon: 34.975 },
	taybad: { lat: 35.1884, lon: 60.7814 },
	sweihan: { lat: 24.4041, lon: 55.3325 },
	mahshahr: { lat: 30.563, lon: 49.198 },
	"bandar khamir": { lat: 26.9592, lon: 55.8981 },
	shalamcheh: { lat: 30.5244, lon: 47.9297 },
	"ramat gan": { lat: 32.0704, lon: 34.8237 },
	shuwaikh: { lat: 29.3636, lon: 47.9417 },
};

const CATEGORY_MAP = {
	cat1: "military",
	cat2: "international",
	cat6: "political",
	cat7: "civil",
	cat9: "intelligence",
	cat10: "airstrike",
	cat11: "defense",
};

function geolocate(title) {
	const lower = title.toLowerCase();
	for (const [name, coords] of Object.entries(LOCATION_COORDS)) {
		if (lower.includes(name)) return { ...coords, locationName: name };
	}
	return { lat: 32.4279, lon: 53.688, locationName: "Iran" };
}

function categorizeSeverity(title) {
	const lower = title.toLowerCase();
	if (/killed|dead|casualties|death toll|wounded/.test(lower)) return "critical";
	if (/airstrike|bombing|missile|explosion|struck|destroyed/.test(lower)) return "high";
	if (/intercept|defense|sirens|alert/.test(lower)) return "elevated";
	return "moderate";
}

function parseRelativeTime(timeStr) {
	const now = Date.now();
	const match = timeStr.match(/(\d+)\s+hours?\s+ago/);
	if (match) return now - parseInt(match[1], 10) * 3600_000;
	const minMatch = timeStr.match(/(\d+)\s+min/);
	if (minMatch) return now - parseInt(minMatch[1], 10) * 60_000;
	if (/a day ago/.test(timeStr)) return now - 86400_000;
	const dayMatch = timeStr.match(/(\d+)\s+days?\s+ago/);
	if (dayMatch) return now - parseInt(dayMatch[1], 10) * 86400_000;
	return now;
}

async function fetchIranEvents() {
	const dataPath = process.argv[2] || join(__dirname, "data", "iran-events-latest.json");
	console.log(`  Reading from: ${dataPath}`);

	const raw = JSON.parse(readFileSync(dataPath, "utf8"));
	const events = raw.filter((e) => e.id && e.title);

	console.log(`  Raw events: ${events.length}`);

	const mapped = events.map((e) => {
		const geo = geolocate(e.title);
		const cat = CATEGORY_MAP[e.category] || "general";
		return {
			id: e.id,
			title: e.title.slice(0, 500),
			category: cat,
			sourceUrl: e.link || "",
			latitude: geo.lat,
			longitude: geo.lon,
			locationName: geo.locationName,
			timestamp: parseRelativeTime(e.time || ""),
			severity: categorizeSeverity(e.title),
		};
	});

	mapped.sort((a, b) => b.timestamp - a.timestamp);

	return {
		events: mapped,
		scrapedAt: Date.now(),
	};
}

function validate(data) {
	return Array.isArray(data?.events) && data.events.length >= 1;
}

runSeed("conflict", "iran-events", CANONICAL_KEY, fetchIranEvents, {
	validateFn: validate,
	ttlSeconds: 172800,
	sourceVersion: "liveuamap-manual-v1",
}).catch((err) => {
	const _cause = err.cause ? ` (cause: ${err.cause.message || err.cause.code || err.cause})` : "";
	console.error("FATAL:", (err.message || err) + _cause);
	process.exit(0);
});
