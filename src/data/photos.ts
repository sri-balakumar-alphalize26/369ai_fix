// Real repair photos supplied by the client (public/media/repairs), keyed 'category:issue'.
// Used on Home and in the cart; anything missing falls back to the device illustration.
export const photo: Record<string, string> = {
  'mobile:Screen replacement': 'screen', 'mobile:Battery replacement': 'battery', 'mobile:Charging port': 'charging',
  'mobile:Back glass': 'backglass', 'mobile:Speaker / microphone': 'speaker', 'mobile:Water damage': 'water', 'mobile:Software & data': 'software', 'mobile:Camera': 'camera',
  'tablet:Screen / glass': 'tab-screen', 'tablet:Display / touch not working': 'tab-display', 'tablet:Battery replacement': 'tab-battery',
  'tablet:Charging port': 'tab-charging', 'tablet:Buttons': 'tab-buttons', 'tablet:Software & data': 'tab-software',
  'laptop:Screen replacement': 'lap-screen', 'laptop:Keyboard / trackpad': 'lap-keyboard', 'laptop:Battery replacement': 'lap-battery',
  'laptop:Hinge repair': 'lap-hinge', 'laptop:Motherboard repair': 'lap-board', 'laptop:Overheating / fan': 'lap-fan', 'laptop:Not powering on': 'lap-power',
  'desktop:Not powering on': 'desk-power-on', 'desktop:Power supply': 'desk-psu', 'desktop:Motherboard repair': 'desk-board',
  'desktop:SSD / RAM upgrade': 'desk-ssd', 'desktop:Graphics card': 'desk-gpu', 'desktop:Custom PC build': 'desk-build',
};
