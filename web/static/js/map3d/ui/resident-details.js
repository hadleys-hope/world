/** Older running servers may omit profile fields added by newer UI versions. */
export function residentDetails(profile, geometry) {
  const sectorIndex = geometry?.houses?.sector?.[profile.home];
  const sector = profile.home_sector ?? (Number.isInteger(sectorIndex) ? sectorIndex + 1 : null);
  const commuteEnabled = typeof profile.commute_enabled === 'boolean'
    ? profile.commute_enabled : sector === 1 && profile.workplace != null;
  return { sector, commuteEnabled };
}
