(() => {
  const translations = {
    en: {
      '3D planet': '3D planet', map: 'map', controllers: 'controllers', house: 'house', systems: 'systems', Attractors: 'Attractors',
      'flat map': 'flat map', 'bus and programs': 'bus and programs', 'Hadley\'s Hope': "Hadley's Hope", Pause: 'Pause', speed: 'speed', Inject: 'Inject', Colony: 'Colony',
      'Reactor and power': 'Reactor and power', Sectors: 'Sectors', 'Open issues': 'Open issues', Events: 'Events', 'Last monthly report': 'Last monthly report',
      '3D map': '3D map', Map: 'Map', Systems: 'Systems', Controllers: 'Controllers', House: 'House', Overview: 'Overview', Layers: 'Layers', Places: 'Places', Operations: 'Operations',
      'Current situation': 'Current situation', Districts: 'Districts', Maintenance: 'Maintenance', 'Event log': 'Event log', 'Monthly report': 'Monthly report',
      'Display controls': 'Display controls', 'Read the city': 'Read the city', World: 'World', Infrastructure: 'Infrastructure', Indicators: 'Indicators', Graphics: 'Graphics',
      Colonists: 'Colonists', 'Threats & marines': 'Threats & marines', 'Place labels': 'Place labels', 'Roof transparency': 'Roof transparency', 'Buried utilities': 'Buried utilities', 'Water flow': 'Water flow', 'Power flow': 'Power flow', 'Data packets': 'Data packets', Faults: 'Faults', 'Offline homes': 'Offline homes', 'UPS activity': 'UPS activity', Heating: 'Heating', 'House programs': 'House programs', 'Light bloom': 'Light bloom', Shadows: 'Shadows',
      'Camera navigation': 'Camera navigation', 'Explore the colony': 'Explore the colony', 'Inspect selected home': 'Inspect selected home', 'Colony overview': 'Colony overview', 'Residential street': 'Residential street', 'Operations hub': 'Operations hub', 'West gate': 'West gate', Reactor: 'Reactor', 'Solar field': 'Solar field', 'Space dish': 'Space dish', 'Ocean intake': 'Ocean intake', Freight: 'Freight', 'Comms tower': 'Comms tower', Mine: 'Mine', Planet: 'Planet', Research: 'Research',
      'Operator console': 'Operator console', 'Simulation controls': 'Simulation controls', 'Operator access': 'Operator access', 'Admin token': 'Admin token', 'Enter token': 'Enter token', 'Enable controls': 'Enable controls', 'House controllers': 'House controllers', 'Scenario events': 'Scenario events', Storm: 'Storm', Xenomorphs: 'Xenomorphs', 'Break power span': 'Break power span', 'Fell pole': 'Fell pole', 'Cut main cable': 'Cut main cable', 'Pump trip': 'Pump trip', 'Marine response': 'Marine response', 'Damage road': 'Damage road', 'Add 50k credits': 'Add 50k credits', 'Reactor SCRAM': 'Reactor SCRAM', 'Found new colony': 'Found new colony',
      'Language': 'Language', English: 'English', Russian: 'Русский', Close: 'Close', 'No month closed yet': 'No month closed yet', 'break span': 'break span', 'fell pole': 'fell pole', xenomorphs: 'xenomorphs', storm: 'storm', 'cut trunk': 'cut trunk', 'pump trip': 'pump trip', 'marines fire': 'marines fire', SCRAM: 'SCRAM', 'break road': 'break road', '+50k cr': '+50k cr', cr: 'cr', kW: 'kW', 'avg C': 'avg C', 'min C': 'min C', pwr: 'pwr', water: 'water', net: 'net', UPS: 'UPS', waste: 'waste', san: 'san', gate: 'gate', road: 'road', 'Hadley\'s Hope, LV-426': "Hadley's Hope, LV-426", 'connecting...': 'connecting...', legend: 'legend', 'Map': 'Map', 'house colour = indoor temperature (blue cold, orange warm), red frame = no power, blue frame = on sector UPS, x = burst pipes.': 'house colour = indoor temperature (blue cold, orange warm), red frame = no power, blue frame = on sector UPS, x = burst pipes.', 'Yellow lines = power (moving dashes = energised), blue = water, cyan = internet cable, cyan dots = packets, red dot = packet with no uplink.': 'Yellow lines = power (moving dashes = energised), blue = water, cyan = internet cable, cyan dots = packets, red dot = packet with no uplink.', 'Poles: dot; orange = tilted, red x = fallen; glow = street lamp on. Gates on the ring road: green open, grey closed, red lockdown.': 'Poles: dot; orange = tilted, red x = fallen; glow = street lamp on. Gates on the ring road: green open, grey closed, red lockdown.', 'Rovers: G garbage, S sludge hauler, E engineers, P plumber. Red diamonds = xenomorphs. ! = open issue.': 'Rovers: G garbage, S sludge hauler, E engineers, P plumber. Red diamonds = xenomorphs. ! = open issue.'
    },
    ru: {
      '3D planet': '3D-планета', map: 'карта', controllers: 'контроллеры', house: 'дом', systems: 'системы', Attractors: 'Аттракторы',
      'flat map': 'плоская карта', 'bus and programs': 'шина и программы', 'Hadley\'s Hope': 'Надежда Хэдли', Pause: 'Пауза', speed: 'скорость', Inject: 'Сценарии', Colony: 'Колония',
      'Reactor and power': 'Реактор и энергия', Sectors: 'Секторы', 'Open issues': 'Открытые проблемы', Events: 'События', 'Last monthly report': 'Последний месячный отчёт',
      '3D map': '3D-карта', Map: 'Карта', Systems: 'Системы', Controllers: 'Контроллеры', House: 'Дом', Overview: 'Обзор', Layers: 'Слои', Places: 'Места', Operations: 'Операции',
      'Current situation': 'Текущая ситуация', Districts: 'Районы', Maintenance: 'Обслуживание', 'Event log': 'Журнал событий', 'Monthly report': 'Месячный отчёт',
      'Display controls': 'Настройки отображения', 'Read the city': 'Изучение города', World: 'Мир', Infrastructure: 'Инфраструктура', Indicators: 'Индикаторы', Graphics: 'Графика',
      Colonists: 'Колонисты', 'Threats & marines': 'Угрозы и морпехи', 'Place labels': 'Подписи мест', 'Roof transparency': 'Прозрачность крыш', 'Buried utilities': 'Подземные коммуникации', 'Water flow': 'Поток воды', 'Power flow': 'Поток энергии', 'Data packets': 'Пакеты данных', Faults: 'Неисправности', 'Offline homes': 'Дома офлайн', 'UPS activity': 'Работа ИБП', Heating: 'Отопление', 'House programs': 'Программы домов', 'Light bloom': 'Свечение', Shadows: 'Тени',
      'Camera navigation': 'Навигация камеры', 'Explore the colony': 'Исследование колонии', 'Inspect selected home': 'Осмотреть выбранный дом', 'Colony overview': 'Обзор колонии', 'Residential street': 'Жилая улица', 'Operations hub': 'Операционный центр', 'West gate': 'Западные ворота', Reactor: 'Реактор', 'Solar field': 'Солнечное поле', 'Space dish': 'Космическая антенна', 'Ocean intake': 'Морской водозабор', Freight: 'Грузовой терминал', 'Comms tower': 'Башня связи', Mine: 'Шахта', Planet: 'Планета', Research: 'Исследования',
      'Operator console': 'Панель оператора', 'Simulation controls': 'Управление симуляцией', 'Operator access': 'Доступ оператора', 'Admin token': 'Токен администратора', 'Enter token': 'Введите токен', 'Enable controls': 'Включить управление', 'House controllers': 'Контроллеры домов', 'Scenario events': 'Сценарии', Storm: 'Шторм', Xenomorphs: 'Ксеноморфы', 'Break power span': 'Повредить линию электропередачи', 'Fell pole': 'Повредить столб', 'Cut main cable': 'Перерезать магистральный кабель', 'Pump trip': 'Отключить насос', 'Marine response': 'Ответ морпехов', 'Damage road': 'Повредить дорогу', 'Add 50k credits': 'Добавить 50 тыс. кредитов', 'Reactor SCRAM': 'Аварийно остановить реактор', 'Found new colony': 'Основать новую колонию',
      'Language': 'Язык', English: 'English', Russian: 'Русский', Close: 'Закрыть', 'No month closed yet': 'Месяц ещё не закрыт', 'break span': 'Повредить линию', 'fell pole': 'Сломать столб', xenomorphs: 'Ксеноморфы', storm: 'Шторм', 'cut trunk': 'Перерезать магистраль', 'pump trip': 'Отключить насос', 'marines fire': 'Огонь морпехов', SCRAM: 'SCRAM', 'break road': 'Повредить дорогу', '+50k cr': '+50 тыс. кр.', cr: 'кр.', kW: 'кВт', 'avg C': 'средняя °C', 'min C': 'минимум °C', pwr: 'питание', water: 'вода', net: 'сеть', UPS: 'ИБП', waste: 'отходы', san: 'санитария', gate: 'ворота', road: 'дорога', 'Hadley\'s Hope, LV-426': 'Надежда Хэдли, LV-426', 'connecting...': 'подключение...', legend: 'легенда', 'Map': 'Карта', 'house colour = indoor temperature (blue cold, orange warm), red frame = no power, blue frame = on sector UPS, x = burst pipes.': 'цвет дома = внутренняя температура (синий — холодно, оранжевый — тепло), красная рамка = нет питания, синяя рамка = ИБП сектора, x = прорванные трубы.', 'Yellow lines = power (moving dashes = energised), blue = water, cyan = internet cable, cyan dots = packets, red dot = packet with no uplink.': 'жёлтые линии = питание (движущиеся штрихи = линия под напряжением), синие = вода, голубые = интернет-кабель, голубые точки = пакеты, красная точка = пакет без восходящего соединения.', 'Poles: dot; orange = tilted, red x = fallen; glow = street lamp on. Gates on the ring road: green open, grey closed, red lockdown.': 'столбы: точка; оранжевый = наклонён, красный x = упал; свечение = уличный фонарь включён. Ворота кольцевой дороги: зелёные открыты, серые закрыты, красные на блокировке.', 'Rovers: G garbage, S sludge hauler, E engineers, P plumber. Red diamonds = xenomorphs. ! = open issue.': 'роверы: G мусоровоз, S ассенизатор, E инженеры, P сантехник. Красные ромбы = ксеноморфы. ! = открытая проблема.'
    }
  };
  Object.assign(translations.ru, {
    "3D view": "3D-вид", "2D view": "2D-вид", Bus: "Шина", Finance: "Финансы", Speed: "Скорость", Console: "Консоль", Resume: "Продолжить",
    Alerts: "Тревоги", "All controls": "Все клавиши", "Look around": "Осмотр", Fly: "Полёт", "Inspect and drive": "Осмотр и вождение",
    orbit: "орбита", "zoom in and out": "приблизить и отдалить", "whole solar system": "вся система", "jump to a planet": "перейти к планете",
    "free flight on / off": "свободный полёт", move: "движение", "down / up": "вниз / вверх", "flight speed": "скорость полёта",
    "lock the mouse": "захватить мышь", "inspect what you point at": "осмотреть объект под курсором", "drive the selected rover": "вести выбранный ровер",
    "park and get out": "припарковаться и выйти", console: "консоль", "this sheet": "эта шпаргалка", fly: "полёт", zoom: "масштаб", inspect: "осмотр",
    "Where the money goes": "Куда идут деньги", "This month": "Этот месяц", "Last month": "Прошлый месяц",
    "Households by cash": "Домохозяйства по деньгам", "Colony budget and household cash": "Бюджет колонии и деньги домохозяйств",
    Colony: "Колония", Water: "Вода", Power: "Питание", Network: "Сеть", "Click a sector": "Нажмите на сектор",
    "Back to the whole colony": "Ко всей колонии", Plants: "Станции", "Operator actions": "Действия оператора",
    "Hadley's Hope: bus and house controllers": "Надежда Хэдли: шина MQTT и контроллеры домов",
    "Hadley's Hope: house": "Надежда Хэдли: дом",
    "Hadley's Hope: systems": "Надежда Хэдли: системы",
    "Hadley's Hope: attractors": "Надежда Хэдли: аттракторы",
    "HADLEY'S HOPE": "НАДЕЖДА ХЭДЛИ",
    "LV–426 · COLONY OPERATIONS": "LV–426 · УПРАВЛЕНИЕ КОЛОНИЕЙ",
    "Main navigation": "Основная навигация",
    "Connecting to colony…": "Подключение к колонии…",
    "DRAG orbit · PINCH zoom · SHIFT toggle free flight · WASD fly · F inspect · M console": "ПЕРЕТАСКИВАНИЕ — орбита · ЩИПOК — масштаб · SHIFT — свободный полёт · WASD — движение · F — осмотр · M — консоль",
    "Planet navigation": "Навигация по планетам",
    "Slower flight": "Медленнее",
    "Faster flight": "Быстрее",
    "ESC · Park & exit": "ESC · Припарковаться и выйти",
    "Show or hide management panel": "Показать или скрыть панель управления",
    "Map view": "Вид карты",
    "Map legend": "Легенда карты",
    "Colony telemetry": "Телеметрия колонии",
    "Current situation": "Текущая ситуация",
    "District data": "Данные районов",
    "Reactor & power": "Реактор и питание",
    "No month closed yet.": "Месяц ещё не закрыт.",
    "Display controls": "Настройки отображения",
    "Read the city": "Изучение города",
    "Select Water below the map to inspect underground pipes. Colours identify separate networks; click a pipe for its material, diameter and live flow.": "Выберите «Вода» под картой, чтобы осмотреть подземные трубы. Цвета обозначают разные сети; нажмите на трубу, чтобы увидеть материал, диаметр и текущий поток.",
    "Camera navigation": "Навигация камеры",
    "Explore the colony": "Исследование колонии",
    "Close views reveal furnished rooms and building services. Enable Roof transparency in Layers to adjust roof translucency; roofs and equipment always remain present.": "При приближении видны комнаты и инженерные системы. Включите «Прозрачность крыш» в разделе «Слои», чтобы настроить прозрачность.",
    "Open attractor observatory →": "Открыть обсерваторию аттракторов →",
    "Operator console": "Панель оператора",
    "Simulation controls": "Управление симуляцией",
    "These actions change the running simulation.": "Эти действия изменяют запущенную симуляцию.",
    "Program comparison, this month": "Сравнение программ за этот месяц",
    "Houses": "Дома", "Bus tail": "Последние сообщения шины", "Topics": "Топики",
    "Power draw right now": "Потребление энергии сейчас", "Last 24 hours": "Последние 24 часа", Facts: "Факты", Controller: "Контроллер", "House log": "Журнал дома",
    "open": "открыть", prev: "назад", next: "далее", "click a header to sort": "нажмите на заголовок для сортировки",
    "indoor temperature, C": "температура внутри, °C", "draw, W": "потребление, Вт", all: "все", sector: "сектор", program: "программа", "house #": "дом №",
    power: "питание", "last decision": "последнее решение", target: "цель", indoor: "внутри", heater: "обогрев", limit: "лимит", valve: "клапан", "sensor age": "возраст датчика", "decision age": "возраст решения",
    "Every house reports its sensors to the bus, its program answers with actuators, the world applies them.": "Каждый дом передаёт датчики на шину, программа отвечает исполнительными командами, а мир применяет их.",
    "No month closed yet": "Месяц ещё не закрыт",
    "Houses": "Дома",
    "Bus tail": "Последние сообщения шины",
    "Topics": "Топики",
    "house #": "дом №",
    "sector": "сектор",
    "program": "программа",
    "houses": "дома",
    "avg indoor C": "средняя температура внутри, °C",
    "kWh per house per day": "кВт·ч на дом в день",
    "cost cr per house per day": "стоимость на дом в день, кр.",
    "time below 16 C": "время ниже 16 °C",
    "comfort": "комфорт",
    "eco": "экономия",
    "night-setback": "ночное снижение",
    "night setback": "ночное снижение",
    "storm-ready": "штормовой режим",
    "thermostat": "термостат",
    "dumb": "простой режим",
    "grid limit, antifreeze": "лимит сети, защита от замерзания",
    "limited power, eco": "ограниченная мощность, экономия",
    "on ups, stretch the battery": "ИБП включён, экономия заряда",
    "storm, banking heat": "шторм, накопление тепла",
    "(offline, last forecast)": "(офлайн, последний прогноз)",
    "Each house reports its sensors to the bus, its program answers with actuators, the world applies them.": "Каждый дом передаёт датчики на шину, программа отвечает командами исполнительных устройств, а мир применяет их.",
    "Same weather, same grid, same houses, only the program differs.": "Одинаковые погода, сеть и дома; отличается только программа.",
    "\"thermostat\" is the built-in fallback for": "«термостат» — встроенный резервный режим для",
    "houses without a live controller.": "домов без активного контроллера.",
    "click a header to sort": "нажмите на заголовок для сортировки",
    "BUS TAIL (every 7th house sampled)": "ШИНА (выборка каждого 7-го дома)",
    "sensor messages": "сообщения датчиков",
    "actuator messages": "сообщения исполнительных устройств",
    "outdoor": "снаружи",
    "bus": "шина",
    "houses under programs": "дома по программам",
    "House controllers": "Контроллеры домов",
    "House log": "Журнал дома",
    "water this month": "вода за этот месяц",
    "energy total": "всего энергии",
    "appliances": "электроприборы",
    "open issues": "открытые проблемы",
    "this month": "в этом месяце",
    "bill so far": "счёт на данный момент",
    "target": "цель",
    "heater off": "обогреватель выключен",
    "power: heater off": "питание: обогреватель выключен",
    "indoor": "внутри",
    "outside": "снаружи",
    "grid": "электросеть",
    "power": "питание",
    "water": "вода",
    "internet": "интернет",
    "online": "в сети",
    "offline": "не в сети",
    "cabinet up": "шкаф управления в сети",
    "flowing online": "поток в сети",
    "water: city tank": "вода: городской резервуар",
    "network: terminal ok": "сеть: терминал в норме",
    "Controller": "Контроллер",
    "decided": "решение принято",
    "3 min ago": "3 мин назад",
    "target 21 C, heater off": "цель 21 °C, обогреватель выключен",
    "rated": "номинал",
    "delivered": "фактически подано",
    "power restored": "электропитание восстановлено",
    "power lost": "электропитание потеряно",
    "network link up": "сетевое соединение восстановлено",
    "network link lost": "сетевое соединение потеряно",
    "pipes frozen": "трубы замёрзли",
    "pipes burst": "трубы прорваны",
    "pipes repaired": "трубы отремонтированы",
    "pipes thawed or repaired": "трубы оттаяли или отремонтированы",
    "no water": "нет воды",
    "water supply restored": "водоснабжение восстановлено",
    "back on the grid": "снова подключён к электросети",
    "running on the sector UPS": "питание от ИБП сектора",
    "power limit imposed by the grid": "сеть ввела ограничение мощности",
    "power limit lifted": "ограничение мощности снято",
    "Power available": "Доступная мощность",
    "Power demand": "Потребление мощности",
    "Colony budget": "Бюджет колонии",
    "Sector budgets": "Бюджеты секторов",
    "Month income (colony)": "Доход за месяц (колония)",
    "Month expense (colony)": "Расходы за месяц (колония)",
    "Water tank": "Резервуар воды",
    "Internet": "Интернет",
    "Pipes": "Трубы",
    "solar": "солнечная энергия",
    "solar field": "солнечное поле",
    "waste processing": "переработка отходов",
    "radioactive waste storage": "хранилище радиоактивных отходов",
    "ONLINE": "В СЕТИ",
    "STANDBY": "ОЖИДАНИЕ",
    "gross": "валовая мощность",
    "to grid": "в сеть",
    "core": "активная зона",
    "pumps": "насосы",
    "heat exchanger": "теплообменник",
    "batteries": "аккумуляторы",
    "link ok": "соединение в норме",
    "trunk ok": "магистраль в норме",
    "substation ok": "подстанция в норме",
    "UPS center": "центр ИБП",
    "loads": "нагрузки",
    "mine": "шахта",
    "water plant": "водоочистная станция",
    "road heating": "обогрев дороги",
    "lamps": "фонари",
    "comms": "связь",
    "ups charge": "заряд ИБП",
    "3D map": "3D-карта",
    "3D planet": "3D-планета",
    "Map view": "Вид карты",
    "Systems": "Системы",
    "Network": "Сеть",
    "Power": "Энергия",
    "Water": "Вода",
    "Thermal": "Тепловой режим",
    "Colour": "Цвет",
    "Thermal basin": "Тепловой бассейн",
    "Attractor observatory": "Обсерватория аттракторов",
    "Power and UPS": "Энергия и ИБП",
    "Flow direction": "Направление потока",
    "Water / direction of flow": "Вода / направление потока",
    "Temperature °C": "Температура, °C",
    "Live · tick": "Онлайн · тик",
    "blackout": "отключение питания",
    "freeze": "замерзание",
    "burst": "прорыв",
    "basin": "бассейн",
    "warm basin": "тёплый бассейн",
    "cannot hold target": "не может удержать цель",
    "will freeze": "замёрзнет",
    "target cannot be maintained at the current heat gains": "цель нельзя поддерживать при текущем притоке тепла",
    "pipes freeze below 0°": "трубы замерзают ниже 0°",
    "pipes burst, waiting for the plumber": "трубы прорваны, ожидается сантехник",
    "one house per district": "один дом на район",
    "selected house": "выбранный дом",
    "margin kW": "резерв мощности, кВт",
    "UPS %": "ИБП, %",
    "full": "полностью заряжен",
    "Outside": "Снаружи",
    "wind": "ветер",
    "warm: settles at its target": "тёплый: стабилизируется на целевой температуре",
    "freeze attractor": "аттрактор замерзания",
    "comfort attractor": "аттрактор комфорта",
    "REACTOR, atmosphere processor": "РЕАКТОР, атмосферный процессор",
    "NETWORK / DATA CENTRE": "СЕТЬ / ЦЕНТР ОБРАБОТКИ ДАННЫХ",
    "OCEAN WATER / MELT · FILTER · DESALINATE": "ОКЕАНСКАЯ ВОДА / ТАЯНИЕ · ФИЛЬТРАЦИЯ · ОПРЕСНЕНИЕ",
    "SHIELDED WASTE / TRANSFER": "ЗАЩИЩЁННЫЕ ОТХОДЫ / ПЕРЕДАЧА",
    "W-02 / TREATED WATER": "W-02 / ОЧИЩЕННАЯ ВОДА",
    "INTAKE SERVICE WALKWAY / RAW WATER + BRINE": "СЛУЖЕБНАЯ ДОРОЖКА ВОДОЗАБОРА / СЫРАЯ ВОДА + РАССОЛ",
    "REACTOR MAINTENANCE": "ОБСЛУЖИВАНИЕ РЕАКТОРА",
    "SOLAR ARRAY / 96 CELL TABLES": "СОЛНЕЧНЫЙ МАССИВ / 96 СЕКЦИЙ",
    "water tank": "резервуар воды",
    "sludge hauler": "ассенизатор",
    "network / data centre": "сеть / центр обработки данных",
    "ocean water treatment": "очистка океанской воды",
    "Current situation": "Текущая ситуация",
    "Events": "События",
    "Scenario events": "События сценария",
    "Event log": "Журнал событий",
    "Last 24 hours": "Последние 24 часа",
    "History": "История",
    "Status": "Состояние",
    "Details": "Подробности",
    "Loading": "Загрузка",
    "Loading...": "Загрузка...",
    "Error": "Ошибка",
    "Warning": "Предупреждение",
    "No data": "Нет данных",
    "open": "открыто",
    "closed": "закрыто",
    "OPEN": "ОТКРЫТО",
    "CLOSED": "ЗАКРЫТО",
    "warning": "предупреждение",
    "NO WATER": "НЕТ ВОДЫ",
    "MARINES IN THE SUBLEVELS": "МОРПЕХИ В ПОДЗЕМНЫХ УРОВНЯХ",
    "comms DOWN": "связь НЕ РАБОТАЕТ",
    "View only. Open the page as /?admin=TOKEN to control the colony.": "Только просмотр. Откройте страницу как /?admin=ТОКЕН для управления колонией.",
    "Water tank empty": "Резервуар воды пуст",
    "Storm is over": "Шторм закончился",
    "CORE DAMAGE. Simulation over.": "ПОВРЕЖДЕНИЕ АКТИВНОЙ ЗОНЫ. Симуляция завершена.",
    "Reactor EMERGENCY: heat removal lost": "АВАРИЯ РЕАКТОРА: отвод тепла потерян",
    "Reactor ONLINE": "Реактор В СЕТИ",
    "Reactor STARTING": "Реактор ЗАПУСКАЕТСЯ",
    "Reactor back ONLINE": "Реактор снова В СЕТИ",
    "Reactor RUNBACK: coolant flow reduced": "РЕАКТОР СНИЖАЕТ МОЩНОСТЬ: поток теплоносителя уменьшен",
    "Reactor core damage": "Повреждение активной зоны реактора",
    "Reactor heat removal restored, COOLING": "Отвод тепла реактора восстановлен, ОХЛАЖДЕНИЕ",
    "Reactor SCRAM": "Аварийная остановка реактора",
    "Reactor pump B tripped": "Насос B реактора отключён",
    "Sector UPS depleted": "ИБП сектора разряжен",
    "Snowstorm for the next 6 hours": "Снежная буря на следующие 6 часов",
    "Xenomorphs outside sector": "Ксеноморфы снаружи сектора",
    "Xenomorphs breached the wall of sector": "Ксеноморфы прорвали стену сектора",
    "Marine squad deployed to sector": "Отряд морпехов направлен в сектор",
    "Marines killed a xenomorph in sector": "Морпехи уничтожили ксеноморфа в секторе",
    "Repair crew attacked by xenomorphs in dark sector": "Ремонтная бригада атакована ксеноморфами в тёмном секторе, ремонт отменён",
    "Rover hit a pole in dark sector": "Ровер врезался в опору в тёмном секторе",
    "Stray marine fire damaged reactor": "Шальная очередь морпеха повредила реактор",
    "Xenomorph nest activity under the atmosphere processor. Marines deployed.": "Под атмосферным процессором обнаружена активность гнезда ксеноморфов. Морпехи направлены на место.",
    "LOCKDOWN": "БЛОКИРОВКА",
    "Garbage rover emptied sector bin": "Мусоровоз очистил контейнер сектора",
    "Sector lockdown lifted": "Блокировка сектора снята",
    "Sector could not pay for waste collection": "Сектор не смог оплатить вывоз отходов",
    "Wait until the crane finishes loading": "Подождите, пока кран закончит погрузку",
    "Colour: red 0 kPa → cyan 600 kPa": "Цвет: красный 0 кПа → голубой 600 кПа",
    "Temperature × thermal rate × pressure · drag to rotate · click a house to inspect": "Температура × скорость изменения температуры × давление · перетаскивайте для вращения · нажмите на дом для осмотра",
    "Thermal phase portrait · click a house to open its details": "Тепловой фазовый портрет · нажмите на дом, чтобы открыть подробности",
    "settles": "стабилизируется",
    "settles at": "стабилизируется на",
    "daily loop": "суточный цикл",
    "if the plant stops": "если станция остановится",
    "first pipes freeze in": "первые трубы замёрзнут через",
    "flow previews hold current weather and power fixed; basins are conditional equilibria, not guaranteed forecasts.": "Предпросмотр потоков фиксирует текущие погоду и мощность; бассейны являются условными равновесиями, а не гарантированными прогнозами.",
    "Dots show measured house states. Thermal view: temperature x °C/h.": "Точки показывают измеренные состояния домов. Тепловой вид: температура × °C/ч.",
    "254 warm, 0 cool, 3 freezing, 43 burst; first pipes freeze in 7.1 h.": "254 тёплых, 0 прохладных, 3 замерзающих, 43 с прорванными трубами; первые трубы замёрзнут через 7,1 ч."
  });


  const cookie = document.cookie.match(/(?:^|; )hh-language=([^;]+)/)?.[1];
  const system = navigator.language?.toLowerCase().startsWith('ru') ? 'ru' : 'en';
  let language = cookie === 'ru' || cookie === 'en' ? cookie : system;
  const translate = (value) => translations[language][value] ?? value;
  window.hhI18n = { get language() { return language; }, t: translate, setLanguage(next) { language = next === 'ru' ? 'ru' : 'en'; document.cookie = `hh-language=${language}; Max-Age=31536000; Path=/; SameSite=Lax`; apply(); } };
  function apply() {
    document.documentElement.lang = language;
    document.title = translate(document.title);
    document.querySelectorAll('[data-i18n]').forEach((node) => { node.textContent = translate(node.dataset.i18n); });
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);
    textNodes.forEach((node) => { const value = node.nodeValue.trim(); if (value && translations.en[value]) node.nodeValue = node.nodeValue.replace(value, translate(value)); });
    document.querySelectorAll('[data-i18n-placeholder]').forEach((node) => { node.placeholder = translate(node.dataset.i18nPlaceholder); });
    document.querySelectorAll('[data-i18n-title]').forEach((node) => { node.title = translate(node.dataset.i18nTitle); });
    document.querySelectorAll('[data-i18n-aria]').forEach((node) => { node.setAttribute('aria-label', translate(node.dataset.i18nAria)); });
    let selector = document.getElementById('language-selector');
    if (!selector) { selector = document.createElement('select'); selector.id = 'language-selector'; selector.setAttribute('aria-label', translate('Language')); selector.innerHTML = '<option value="en">EN</option><option value="ru">RU</option>'; selector.value = language; selector.addEventListener('change', () => { window.hhI18n.setLanguage(selector.value); selector.blur(); }); (document.getElementById('lang-slot') || document.body).append(selector); }
    selector.value = language;
  }
  const start = () => {
    document.querySelectorAll('body *:not(script):not(style)').forEach((node) => {
      if (node.children.length === 0 && node.textContent.trim() && !node.dataset.i18n) node.dataset.i18n = node.textContent.trim();
    });
    document.querySelectorAll('[aria-label]:not([data-i18n-aria]), [title]:not([data-i18n-title]), [placeholder]:not([data-i18n-placeholder])').forEach((node) => {
      if (node.getAttribute('aria-label')) node.dataset.i18nAria = node.getAttribute('aria-label');
      if (node.getAttribute('title')) node.dataset.i18nTitle = node.getAttribute('title');
      if (node.getAttribute('placeholder')) node.dataset.i18nPlaceholder = node.getAttribute('placeholder');
    });
    apply();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();

  // Translate known Russian strings added dynamically without modifying the language selector.
  const dynamicObserver = new MutationObserver((records) => {
    if (language !== 'ru') return;
    for (const record of records) {
      const nodes = [];
      if (record.type === 'characterData') nodes.push(record.target);
      else record.addedNodes.forEach((node) => {
        if (node.nodeType === Node.TEXT_NODE) nodes.push(node);
        else if (node.nodeType === Node.ELEMENT_NODE && !node.closest('script,style')) {
          const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
          while (walker.nextNode()) nodes.push(walker.currentNode);
          ['title', 'aria-label', 'placeholder'].forEach((attr) => {
            const val = node.getAttribute(attr);
            if (val && translations.ru[val] && translations.ru[val] !== val) node.setAttribute(attr, translations.ru[val]);
          });
        }
      });
      nodes.forEach((node) => {
        const raw = node.nodeValue;
        if (!raw) return;
        const trimmed = raw.trim();
        if (trimmed && translations.ru[trimmed] && translations.ru[trimmed] !== trimmed) node.nodeValue = raw.replace(trimmed, translations.ru[trimmed]);
      });
    }
  });
  const beginDynamicTranslation = () => {
    if (document.body) dynamicObserver.observe(document.body, {subtree: true, childList: true, characterData: true});
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', beginDynamicTranslation);
  else beginDynamicTranslation();
})();
