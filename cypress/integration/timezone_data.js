import "../../frappe/public/js/lib/moment";

describe("Timezone data", () => {
	it("converts historical dates between system and user zones across DST", () => {
		const moment = window.moment;
		for (const [system_datetime, user_datetime] of [
			["2000-01-01 12:00:00", "2000-01-01 04:00:00"],
			["2000-07-01 12:00:00", "2000-07-01 05:00:00"],
		]) {
			const converted = moment.tz(system_datetime, "Africa/Nairobi").tz("America/New_York");
			expect(converted.format("YYYY-MM-DD HH:mm:ss")).to.equal(user_datetime);
			expect(converted.tz("Africa/Nairobi").format("YYYY-MM-DD HH:mm:ss")).to.equal(
				system_datetime
			);
		}
	});
});
