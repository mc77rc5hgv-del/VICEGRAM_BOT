#!/usr/bin/env python3
"""
Generates skull_metadata.json from the bone/structure nomenclature in the TOR
(section 3), validated against skull_metadata.schema.json.

This encodes standard TA2 / Gaivoronskiy nomenclature (static reference
knowledge). It does NOT encode real per-specimen geometry, measurements, or
mesh data — those require the actual CT-reconstruction pipeline described in
pipeline/README.md. `mesh_ref` is left null until real geometry exists.

Usage:
    python3 generate_metadata.py [--validate]
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_PATH = HERE / "skull_metadata.json"
SCHEMA_PATH = HERE / "schema" / "skull_metadata.schema.json"

# ---------------------------------------------------------------------------
# Bones (раздел 3.1-3.2: 23 кости + нижняя челюсть + подъязычная кость)
# ---------------------------------------------------------------------------

BONES = [
    # Neurocranium
    dict(id="os_frontale", ta2_latin="Os frontale", name_ru="Лобная кость",
         region="neurocranium", side="midline"),
    dict(id="os_parietale_dex", ta2_latin="Os parietale (dextrum)", name_ru="Теменная кость (правая)",
         region="neurocranium", side="right"),
    dict(id="os_parietale_sin", ta2_latin="Os parietale (sinistrum)", name_ru="Теменная кость (левая)",
         region="neurocranium", side="left"),
    dict(id="os_occipitale", ta2_latin="Os occipitale", name_ru="Затылочная кость",
         region="neurocranium", side="midline"),
    dict(id="os_sphenoidale", ta2_latin="Os sphenoidale", name_ru="Клиновидная кость",
         region="neurocranium", side="midline"),
    dict(id="os_temporale_dex", ta2_latin="Os temporale (dextrum)", name_ru="Височная кость (правая)",
         region="neurocranium", side="right"),
    dict(id="os_temporale_sin", ta2_latin="Os temporale (sinistrum)", name_ru="Височная кость (левая)",
         region="neurocranium", side="left"),
    dict(id="os_ethmoidale", ta2_latin="Os ethmoidale", name_ru="Решётчатая кость",
         region="neurocranium", side="midline"),
    # Viscerocranium
    dict(id="maxilla_dex", ta2_latin="Maxilla (dextra)", name_ru="Верхняя челюсть (правая)",
         region="viscerocranium", side="right"),
    dict(id="maxilla_sin", ta2_latin="Maxilla (sinistra)", name_ru="Верхняя челюсть (левая)",
         region="viscerocranium", side="left"),
    dict(id="mandibula", ta2_latin="Mandibula", name_ru="Нижняя челюсть",
         region="viscerocranium", side="midline", movable=True),
    dict(id="os_zygomaticum_dex", ta2_latin="Os zygomaticum (dextrum)", name_ru="Скуловая кость (правая)",
         region="viscerocranium", side="right"),
    dict(id="os_zygomaticum_sin", ta2_latin="Os zygomaticum (sinistrum)", name_ru="Скуловая кость (левая)",
         region="viscerocranium", side="left"),
    dict(id="os_nasale_dex", ta2_latin="Os nasale (dextrum)", name_ru="Носовая кость (правая)",
         region="viscerocranium", side="right"),
    dict(id="os_nasale_sin", ta2_latin="Os nasale (sinistrum)", name_ru="Носовая кость (левая)",
         region="viscerocranium", side="left"),
    dict(id="os_lacrimale_dex", ta2_latin="Os lacrimale (dextrum)", name_ru="Слёзная кость (правая)",
         region="viscerocranium", side="right"),
    dict(id="os_lacrimale_sin", ta2_latin="Os lacrimale (sinistrum)", name_ru="Слёзная кость (левая)",
         region="viscerocranium", side="left"),
    dict(id="os_palatinum_dex", ta2_latin="Os palatinum (dextrum)", name_ru="Нёбная кость (правая)",
         region="viscerocranium", side="right"),
    dict(id="os_palatinum_sin", ta2_latin="Os palatinum (sinistrum)", name_ru="Нёбная кость (левая)",
         region="viscerocranium", side="left"),
    dict(id="concha_nasalis_inferior_dex", ta2_latin="Concha nasalis inferior (dextra)",
         name_ru="Нижняя носовая раковина (правая)", region="viscerocranium", side="right"),
    dict(id="concha_nasalis_inferior_sin", ta2_latin="Concha nasalis inferior (sinistra)",
         name_ru="Нижняя носовая раковина (левая)", region="viscerocranium", side="left"),
    dict(id="vomer", ta2_latin="Vomer", name_ru="Сошник",
         region="viscerocranium", side="midline"),
    # Hyoid (not part of the 22-bone skull proper, but required by section 3.2 / 7)
    dict(id="os_hyoideum", ta2_latin="Os hyoideum", name_ru="Подъязычная кость",
         region="hyoid", side="midline"),
]

# ---------------------------------------------------------------------------
# Structures (раздел 3.1-3.4). Each tuple:
# (id_suffix, category, ta2_latin, name_ru, side, description, contents, clinical_note)
# ---------------------------------------------------------------------------

def s(id_suffix, category, ta2_latin, name_ru, description, side=None, contents=None, clinical_note=None):
    return dict(id_suffix=id_suffix, category=category, ta2_latin=ta2_latin, name_ru=name_ru,
                side=side, description=description, contents=contents, clinical_note=clinical_note)

STRUCTURES_BY_BONE = {
    "os_frontale": [
        s("squama_frontalis", "surface", "Squama frontalis", "Чешуя лобной кости",
          "Выпуклая пластинка, образующая лоб."),
        s("pars_orbitalis", "plate", "Pars orbitalis", "Глазничная часть", "Образует верхнюю стенку глазницы.",
          side="paired"),
        s("pars_nasalis", "surface", "Pars nasalis", "Носовая часть", "Соединяется с носовыми костями."),
        s("tuber_frontale", "tubercle", "Tuber frontale", "Лобный бугор", "Выступ чешуи, ориентир возраста/пола.",
          side="paired"),
        s("arcus_superciliaris", "crest", "Arcus superciliaris", "Надбровная дуга", "Валик над глазницей.",
          side="paired"),
        s("glabella", "other", "Glabella", "Глабелла (надпереносье)",
          "Площадка между надбровными дугами, краниометрическая точка."),
        s("facies_orbitalis", "surface", "Facies orbitalis", "Глазничная поверхность", "Верхняя стенка глазницы."),
        s("fossa_glandulae_lacrimalis", "fossa", "Fossa glandulae lacrimalis", "Ямка слёзной железы",
          "Углубление в латеральной части глазничной поверхности для слёзной железы."),
        s("fovea_trochlearis", "fossa", "Fovea/spina trochlearis", "Блоковая ямка/ость",
          "Место прикрепления хряща блока верхней косой мышцы глаза."),
        s("sinus_frontalis", "cavity", "Sinus frontalis", "Лобная пазуха",
          "Воздухоносная полость в чешуе, дренируется в средний носовой ход.",
          contents="слизистая оболочка, воздух",
          clinical_note="частая локализация фронтита"),
        s("foramen_incisura_supraorbitalis", "foramen", "Foramen/incisura supraorbitalis",
          "Надглазничное отверстие/вырезка", "На верхнем крае глазницы.",
          contents="n. supraorbitalis, a./v. supraorbitalis"),
        s("incisura_frontalis", "notch", "Incisura frontalis", "Лобная вырезка", "Медиальнее надглазничной вырезки.",
          contents="n. supratrochlearis"),
        s("processus_zygomaticus", "process", "Processus zygomaticus", "Скуловой отросток",
          "Соединяется со скуловой костью.", side="paired"),
        s("linea_temporalis", "line", "Linea temporalis", "Височная линия",
          "Дугообразная линия, начало височной фасции."),
    ],
    "os_parietale_dex": [
        s("margo_frontalis", "margin", "Margo frontalis", "Лобный край", "Соединяется с лобной костью."),
        s("margo_occipitalis", "margin", "Margo occipitalis", "Затылочный край", "Соединяется с затылочной костью."),
        s("margo_sagittalis", "margin", "Margo sagittalis", "Сагиттальный край", "Соединяется с противоположной теменной костью."),
        s("margo_squamosus", "margin", "Margo squamosus", "Чешуйчатый край", "Соединяется с височной костью."),
        s("angulus_frontalis", "angle", "Angulus frontalis", "Лобный угол", "Передневерхний угол кости."),
        s("angulus_occipitalis", "angle", "Angulus occipitalis", "Затылочный угол", "Задневерхний угол кости."),
        s("angulus_sphenoidalis", "angle", "Angulus sphenoidalis", "Клиновидный угол", "Передненижний угол кости."),
        s("angulus_mastoideus", "angle", "Angulus mastoideus", "Сосцевидный угол", "Задненижний угол кости."),
        s("linea_temporalis_superior", "line", "Linea temporalis superior", "Верхняя височная линия",
          "Начало височной фасции."),
        s("linea_temporalis_inferior", "line", "Linea temporalis inferior", "Нижняя височная линия",
          "Начало височной мышцы."),
        s("tuber_parietale", "tubercle", "Tuber parietale", "Теменной бугор", "Наиболее выпуклая часть кости."),
        s("sulcus_arteriae_meningeae_mediae", "sulcus", "Sulcus arteriae meningeae mediae",
          "Борозда средней менингеальной артерии", "На внутренней поверхности кости.",
          contents="a. meningea media"),
        s("foramen_parietale", "foramen", "Foramen parietale", "Теменное отверстие",
          "Вблизи сагиттального края.", contents="выпускник (v. emissaria parietalis)"),
    ],
    "os_occipitale": [
        s("squama_occipitalis", "surface", "Squama occipitalis", "Чешуя затылочной кости", "Задняя часть кости."),
        s("partes_laterales", "other", "Partes laterales", "Латеральные части", "Несут затылочные мыщелки.",
          side="paired"),
        s("pars_basilaris", "other", "Pars basilaris", "Базилярная часть", "Соединяется с телом клиновидной кости, образуя скат."),
        s("foramen_magnum", "foramen", "Foramen magnum", "Большое затылочное отверстие",
          "Соединяет полость черепа с позвоночным каналом.",
          contents="продолговатый мозг, позвоночные артерии, добавочный нерв (XI)"),
        s("condylus_occipitalis", "process", "Condylus occipitalis", "Затылочный мыщелок",
          "Сочленяется с атлантом.", side="paired"),
        s("canalis_condylaris", "canal", "Canalis condylaris", "Мыщелковый канал", "Позади мыщелка.",
          side="paired", contents="v. emissaria condylaris"),
        s("canalis_hypoglossalis", "canal", "Canalis nervi hypoglossi", "Канал подъязычного нерва",
          "Над основанием мыщелка.", side="paired", contents="n. hypoglossus (XII)"),
        s("incisura_jugularis", "notch", "Incisura jugularis", "Яремная вырезка",
          "Образует яремное отверстие с височной костью.", side="paired"),
        s("processus_jugularis", "process", "Processus jugularis", "Ярёмный отросток", "Латеральнее вырезки.",
          side="paired"),
        s("protuberantia_occipitalis_externa", "protuberance", "Protuberantia occipitalis externa",
          "Наружный затылочный выступ", "Пальпируемый ориентир (иниона)."),
        s("protuberantia_occipitalis_interna", "protuberance", "Protuberantia occipitalis interna",
          "Внутренний затылочный выступ", "Место слияния синусов (confluens sinuum)."),
        s("crista_occipitalis_externa", "crest", "Crista occipitalis externa", "Наружный затылочный гребень",
          "От внешнего выступа к большому затылочному отверстию."),
        s("crista_occipitalis_interna", "crest", "Crista occipitalis interna", "Внутренний затылочный гребень",
          "Место прикрепления серпа мозжечка."),
        s("linea_nuchalis_superior", "line", "Linea nuchalis superior", "Верхняя выйная линия",
          "Место прикрепления мышц шеи/спины."),
        s("linea_nuchalis_inferior", "line", "Linea nuchalis inferior", "Нижняя выйная линия",
          "Ниже верхней выйной линии."),
        s("clivus", "surface", "Clivus", "Скат",
          "Наклонная поверхность из базилярной части затылочной и тела клиновидной костей.",
          contents="мост, продолговатый мозг прилежат сверху"),
        s("sulcus_sinus_transversi", "sulcus", "Sulcus sinus transversi", "Борозда поперечного синуса",
          "На внутренней поверхности чешуи.", contents="sinus transversus"),
        s("sulcus_sinus_sigmoidei", "sulcus", "Sulcus sinus sigmoidei", "Борозда сигмовидного синуса",
          "Продолжение борозды поперечного синуса.", contents="sinus sigmoideus", side="paired"),
    ],
    "os_sphenoidale": [
        s("corpus", "other", "Corpus ossis sphenoidalis", "Тело клиновидной кости", "Центральная часть, содержит пазуху."),
        s("ala_major", "process", "Ala major", "Большое крыло", "Образует часть боковой стенки черепа и глазницы.",
          side="paired"),
        s("ala_minor", "process", "Ala minor", "Малое крыло", "Образует часть передней черепной ямки.",
          side="paired"),
        s("processus_pterygoideus", "process", "Processus pterygoideus", "Крыловидный отросток",
          "Спускается от тела книзу.", side="paired"),
        s("tuberculum_sellae", "other", "Tuberculum sellae", "Бугорок седла", "Передняя граница турецкого седла."),
        s("dorsum_sellae", "other", "Dorsum sellae", "Спинка седла", "Задняя стенка турецкого седла."),
        s("fossa_hypophysialis", "fossa", "Fossa hypophysialis", "Гипофизарная ямка",
          "Вмещает гипофиз (турецкое седло).", contents="гипофиз"),
        s("sulcus_caroticus", "sulcus", "Sulcus caroticus", "Сонная борозда", "На боковой поверхности тела.",
          side="paired", contents="a. carotis interna, plexus caroticus internus"),
        s("sinus_sphenoidalis", "cavity", "Sinus sphenoidalis", "Клиновидная пазуха",
          "Воздухоносная полость тела кости, разделена перегородкой (septum sinuum sphenoidalium)."),
        s("canalis_opticus", "canal", "Canalis opticus", "Зрительный канал", "У основания малого крыла.",
          side="paired", contents="n. opticus (II), a. ophthalmica"),
        s("fissura_orbitalis_superior", "fissure", "Fissura orbitalis superior", "Верхняя глазничная щель",
          "Между большим и малым крылом.", side="paired",
          contents="n. III, IV, VI, n. ophthalmicus (V1), v. ophthalmica superior"),
        s("foramen_rotundum", "foramen", "Foramen rotundum", "Круглое отверстие", "В большом крыле.",
          side="paired", contents="n. maxillaris (V2)"),
        s("foramen_ovale", "foramen", "Foramen ovale", "Овальное отверстие", "В большом крыле.",
          side="paired", contents="n. mandibularis (V3)"),
        s("foramen_spinosum", "foramen", "Foramen spinosum", "Остистое отверстие", "Позади овального отверстия.",
          side="paired", contents="a. meningea media"),
        s("canalis_pterygoideus", "canal", "Canalis pterygoideus", "Крыловидный канал",
          "У основания крыловидного отростка.", side="paired", contents="n. canalis pterygoidei (видиев нерв)"),
        s("fossa_pterygoidea", "fossa", "Fossa pterygoidea", "Крыловидная ямка",
          "Между пластинками крыловидного отростка.", side="paired"),
        s("fossa_scaphoidea", "fossa", "Fossa scaphoidea", "Ладьевидная ямка",
          "У основания медиальной пластинки.", side="paired"),
        s("lamina_medialis_processus_pterygoidei", "plate", "Lamina medialis processus pterygoidei",
          "Медиальная пластинка крыловидного отростка", "Оканчивается крыловидным крючком.", side="paired"),
        s("lamina_lateralis_processus_pterygoidei", "plate", "Lamina lateralis processus pterygoidei",
          "Латеральная пластинка крыловидного отростка", "Место начала крыловидных мышц.", side="paired"),
        s("hamulus_pterygoideus", "process", "Hamulus pterygoideus", "Крыловидный крючок",
          "Огибает сухожилие мышцы, напрягающей нёбную занавеску.", side="paired"),
    ],
    "os_temporale_dex": [
        s("pars_squamosa", "other", "Pars squamosa", "Чешуйчатая часть", "Плоская часть, участвует в своде черепа."),
        s("pars_tympanica", "other", "Pars tympanica", "Барабанная часть", "Окружает наружный слуховой проход."),
        s("pars_petrosa", "other", "Pars petrosa (pyramis)", "Каменистая часть (пирамида)",
          "Содержит структуры среднего и внутреннего уха."),
        s("processus_mastoideus", "process", "Processus mastoideus", "Сосцевидный отросток",
          "Место прикрепления грудино-ключично-сосцевидной мышцы."),
        s("processus_zygomaticus", "process", "Processus zygomaticus", "Скуловой отросток",
          "Соединяется со скуловой костью, образуя скуловую дугу."),
        s("fossa_mandibularis", "fossa", "Fossa mandibularis", "Нижнечелюстная ямка",
          "Сочленяется с мыщелковым отростком нижней челюсти (ВНЧС).",
          clinical_note="компонент височно-нижнечелюстного сустава"),
        s("tuberculum_articulare", "tubercle", "Tuberculum articulare", "Суставной бугорок",
          "Кпереди от нижнечелюстной ямки."),
        s("meatus_acusticus_externus", "canal", "Meatus acusticus externus", "Наружный слуховой проход",
          "Ведёт к барабанной перепонке."),
        s("meatus_acusticus_internus", "canal", "Meatus acusticus internus", "Внутренний слуховой проход",
          "На задней поверхности пирамиды.", contents="n. facialis (VII), n. vestibulocochlearis (VIII), a. labyrinthi"),
        s("processus_styloideus", "process", "Processus styloideus", "Шиловидный отросток",
          "Место прикрепления шилоязычной, шилоподъязычной, шилоглоточной мышц и связок."),
        s("foramen_stylomastoideum", "foramen", "Foramen stylomastoideum", "Шилососцевидное отверстие",
          "Между шиловидным и сосцевидным отростками.", contents="n. facialis (VII)"),
        s("canalis_caroticus", "canal", "Canalis caroticus", "Сонный канал", "В пирамиде.",
          contents="a. carotis interna, plexus caroticus internus"),
        s("canalis_musculotubarius", "canal", "Canalis musculotubarius", "Мышечно-трубный канал",
          "Содержит полуканалы слуховой трубы и мышцы, напрягающей барабанную перепонку."),
        s("canalis_facialis", "canal", "Canalis facialis", "Лицевой канал",
          "С коленцем (geniculum canalis facialis), ведёт к шилососцевидному отверстию.",
          contents="n. facialis (VII)"),
        s("canaliculus_nervi_petrosi_majoris", "canal", "Canaliculus nervi petrosi majoris",
          "Канал большого каменистого нерва", "Отходит от коленца лицевого канала.",
          contents="n. petrosus major"),
        s("canaliculus_nervi_petrosi_minoris", "canal", "Canaliculus nervi petrosi minoris",
          "Канал малого каменистого нерва", "Параллельно каналу большого каменистого нерва.",
          contents="n. petrosus minor"),
        s("fossa_jugularis", "fossa", "Fossa jugularis", "Ярёмная ямка",
          "На нижней поверхности пирамиды, образует яремное отверстие с затылочной костью.",
          contents="v. jugularis interna (луковица)"),
        s("incisura_mastoidea", "notch", "Incisura mastoidea", "Сосцевидная вырезка",
          "Медиальнее сосцевидного отростка, место начала двубрюшной мышцы."),
        s("sulcus_sinus_sigmoidei", "sulcus", "Sulcus sinus sigmoidei", "Борозда сигмовидного синуса",
          "На внутренней поверхности сосцевидной части.", contents="sinus sigmoideus"),
        s("eminentia_arcuata", "other", "Eminentia arcuata", "Дугообразное возвышение",
          "На передней поверхности пирамиды, соответствует переднему полукружному каналу."),
        s("tegmen_tympani", "plate", "Tegmen tympani", "Крыша барабанной полости",
          "Тонкая костная пластинка, отделяющая барабанную полость от средней черепной ямки."),
        s("cellulae_mastoideae", "cavity", "Cellulae mastoideae", "Сосцевидные ячейки",
          "Воздухоносные ячейки сосцевидного отростка, сообщаются с сосцевидной пещерой и барабанной полостью."),
    ],
    "os_ethmoidale": [
        s("lamina_cribrosa", "plate", "Lamina cribrosa", "Решётчатая (дырчатая) пластинка",
          "Отверстия для обонятельных нитей.", contents="fila olfactoria (n. I)"),
        s("crista_galli", "process", "Crista galli", "Петушиный гребень",
          "Место прикрепления серпа большого мозга."),
        s("lamina_perpendicularis", "plate", "Lamina perpendicularis", "Перпендикулярная пластинка",
          "Участвует в костной перегородке носа."),
        s("lamina_orbitalis", "plate", "Lamina orbitalis (papyracea)", "Глазничная (бумажная) пластинка",
          "Образует медиальную стенку глазницы.", side="paired"),
        s("concha_nasalis_superior", "other", "Concha nasalis superior", "Верхняя носовая раковина",
          "Часть решётчатого лабиринта.", side="paired"),
        s("concha_nasalis_media", "other", "Concha nasalis media", "Средняя носовая раковина",
          "Часть решётчатого лабиринта.", side="paired"),
        s("labyrinthus_ethmoidalis", "cavity", "Labyrinthus ethmoidalis, cellulae ethmoidales",
          "Решётчатый лабиринт и ячейки", "Воздухоносные ячейки между глазницей и полостью носа.",
          side="paired"),
        s("processus_uncinatus", "process", "Processus uncinatus", "Крючковидный отросток",
          "Участвует в остиомеатальном комплексе, ограничивает полулунную щель.", side="paired"),
    ],
    "maxilla_dex": [
        s("corpus", "other", "Corpus maxillae", "Тело верхней челюсти", "Содержит верхнечелюстную пазуху."),
        s("sinus_maxillaris", "cavity", "Sinus maxillaris", "Верхнечелюстная пазуха (гайморова)",
          "Наибольшая околоносовая пазуха, дренируется в средний носовой ход."),
        s("processus_frontalis", "process", "Processus frontalis", "Лобный отросток",
          "Соединяется с лобной, носовой, слёзной костями."),
        s("processus_zygomaticus", "process", "Processus zygomaticus", "Скуловой отросток",
          "Соединяется со скуловой костью."),
        s("processus_palatinus", "process", "Processus palatinus", "Нёбный отросток",
          "Образует переднюю часть твёрдого нёба."),
        s("processus_alveolaris", "process", "Processus alveolaris", "Альвеолярный отросток",
          "Несёт зубные альвеолы верхних зубов."),
        s("margo_infraorbitalis", "margin", "Margo infraorbitalis", "Подглазничный край", "Нижний край глазницы."),
        s("foramen_canalis_infraorbitalis", "foramen", "Foramen infraorbitale, canalis infraorbitalis",
          "Подглазничное отверстие и канал", "На передней поверхности тела.",
          contents="n. infraorbitalis, a./v. infraorbitalis"),
        s("fossa_canina", "fossa", "Fossa canina", "Клыковая ямка",
          "Углубление передней поверхности, место начала мышцы, поднимающей угол рта."),
        s("tuber_maxillae", "tubercle", "Tuber maxillae", "Бугор верхней челюсти",
          "Задняя выпуклость тела, содержит альвеолярные отверстия.",
          contents="rr. alveolares superiores posteriores"),
        s("foramen_canalis_palatinus_major", "canal", "Foramen palatinum majus, canalis palatinus major",
          "Большое нёбное отверстие и канал", "На нёбном отростке у заднего края.",
          contents="n./a. palatina major"),
        s("foramen_canalis_incisivus", "canal", "Foramen incisivum, canalis incisivus",
          "Резцовое отверстие и канал", "В переднем отделе твёрдого нёба.",
          contents="n. nasopalatinus, a. sphenopalatina (ветви)"),
        s("juga_alveolaria", "other", "Juga alveolaria", "Альвеолярные возвышения",
          "Выпуклости на передней поверхности над корнями зубов."),
        s("alveoli_dentales", "other", "Alveoli dentales", "Зубные альвеолы",
          "Ячейки альвеолярного отростка для корней зубов."),
    ],
    "mandibula": [
        s("corpus", "other", "Corpus mandibulae", "Тело нижней челюсти", "Горизонтальная часть."),
        s("ramus", "other", "Ramus mandibulae", "Ветвь нижней челюсти", "Вертикальная часть.", side="paired"),
        s("angulus", "angle", "Angulus mandibulae", "Угол нижней челюсти",
          "Место перехода тела в ветвь.", side="paired"),
        s("pars_alveolaris", "other", "Pars alveolaris", "Альвеолярная часть", "Несёт зубные альвеолы нижних зубов."),
        s("protuberantia_mentalis", "protuberance", "Protuberantia mentalis", "Подбородочный выступ",
          "Передний отдел тела, признак вида Homo sapiens."),
        s("tuberculum_mentale", "tubercle", "Tuberculum mentale", "Подбородочный бугорок",
          "По бокам подбородочного выступа.", side="paired"),
        s("foramen_mentale", "foramen", "Foramen mentale", "Подбородочное отверстие",
          "На наружной поверхности тела.", side="paired", contents="n. mentalis, a./v. mentalis"),
        s("linea_obliqua", "line", "Linea obliqua", "Косая линия",
          "На наружной поверхности тела, продолжение переднего края ветви.", side="paired"),
        s("linea_mylohyoidea", "line", "Linea mylohyoidea", "Челюстно-подъязычная линия",
          "На внутренней поверхности тела, начало челюстно-подъязычной мышцы.", side="paired"),
        s("processus_coronoideus", "process", "Processus coronoideus", "Венечный отросток",
          "Место прикрепления височной мышцы.", side="paired"),
        s("processus_condylaris", "process", "Processus condylaris", "Мыщелковый отросток",
          "Сочленяется с нижнечелюстной ямкой височной кости (ВНЧС).", side="paired"),
        s("incisura_mandibulae", "notch", "Incisura mandibulae", "Вырезка нижней челюсти",
          "Между венечным и мыщелковым отростками.", side="paired"),
        s("foramen_mandibulae", "foramen", "Foramen mandibulae", "Отверстие нижней челюсти",
          "На внутренней поверхности ветви, вход в канал нижней челюсти.",
          side="paired", contents="n. alveolaris inferior, a./v. alveolaris inferior"),
        s("lingula_mandibulae", "process", "Lingula mandibulae", "Язычок нижней челюсти",
          "Костный выступ у отверстия нижней челюсти, ориентир для мандибулярной анестезии.",
          side="paired", clinical_note="ориентир мандибулярной анестезии"),
        s("sulcus_mylohyoideus", "sulcus", "Sulcus mylohyoideus", "Челюстно-подъязычная борозда",
          "Ниже отверстия нижней челюсти.", side="paired", contents="n., a. mylohyoidea"),
        s("fovea_pterygoidea", "fossa", "Fovea pterygoidea", "Крыловидная ямка",
          "На внутренней поверхности мыщелкового отростка, место прикрепления латеральной крыловидной мышцы.",
          side="paired"),
    ],
    "os_zygomaticum_dex": [
        s("facies_lateralis", "surface", "Facies lateralis", "Латеральная поверхность", "Формирует контур скулы."),
        s("facies_orbitalis", "surface", "Facies orbitalis", "Глазничная поверхность",
          "Участвует в латеральной стенке и дне глазницы."),
        s("facies_temporalis", "surface", "Facies temporalis", "Височная поверхность",
          "Обращена в височную ямку."),
        s("foramen_zygomaticofaciale", "foramen", "Foramen zygomaticofaciale", "Скулолицевое отверстие",
          "На латеральной поверхности.", contents="r. zygomaticofacialis (n. zygomaticus)"),
        s("foramen_zygomaticoorbitale", "foramen", "Foramen zygomaticoorbitale", "Скулоглазничное отверстие",
          "На глазничной поверхности.", contents="n. zygomaticus"),
        s("foramen_zygomaticotemporale", "foramen", "Foramen zygomaticotemporale", "Скуловисочное отверстие",
          "На височной поверхности.", contents="r. zygomaticotemporalis (n. zygomaticus)"),
        s("processus_frontalis", "process", "Processus frontalis", "Лобный отросток",
          "Соединяется со скуловым отростком лобной кости."),
        s("processus_temporalis", "process", "Processus temporalis", "Височный отросток",
          "Соединяется со скуловым отростком височной кости, образуя скуловую дугу."),
    ],
    "os_nasale_dex": [
        s("facies_externa", "surface", "Facies externa", "Передняя поверхность", "Гладкая, пальпируемая."),
        s("facies_interna", "surface", "Facies interna", "Задняя поверхность", "Обращена в полость носа."),
        s("sulcus_ethmoidalis", "sulcus", "Sulcus ethmoidalis", "Решётчатая борозда",
          "На внутренней поверхности.", contents="n. ethmoidalis anterior"),
    ],
    "os_lacrimale_dex": [
        s("crista_lacrimalis_posterior", "crest", "Crista lacrimalis posterior", "Задний слёзный гребень",
          "Ограничивает слёзную борозду сзади."),
        s("sulcus_lacrimalis", "sulcus", "Sulcus lacrimalis", "Слёзная борозда",
          "Формирует часть ямки слёзного мешка."),
        s("hamulus_lacrimalis", "process", "Hamulus lacrimalis", "Слёзный крючок",
          "Нижний конец заднего слёзного гребня."),
    ],
    "os_palatinum_dex": [
        s("lamina_horizontalis", "plate", "Lamina horizontalis", "Горизонтальная пластинка",
          "Образует заднюю часть твёрдого нёба."),
        s("lamina_perpendicularis", "plate", "Lamina perpendicularis", "Перпендикулярная пластинка",
          "Участвует в латеральной стенке полости носа."),
        s("sulcus_palatinus_major", "sulcus", "Sulcus palatinus major", "Большая нёбная борозда",
          "Формирует часть большого нёбного канала.", contents="n./a. palatina major"),
        s("processus_sphenoidalis", "process", "Processus sphenoidalis", "Клиновидный отросток",
          "Соединяется с телом клиновидной кости."),
        s("processus_orbitalis", "process", "Processus orbitalis", "Глазничный отросток",
          "Участвует в дне глазницы."),
        s("processus_pyramidalis", "process", "Processus pyramidalis", "Пирамидальный отросток",
          "Заполняет промежуток между пластинками крыловидного отростка."),
    ],
    "concha_nasalis_inferior_dex": [
        s("processus_lacrimalis", "process", "Processus lacrimalis", "Слёзный отросток",
          "Соединяется со слёзной костью."),
        s("processus_maxillaris", "process", "Processus maxillaris", "Верхнечелюстной отросток",
          "Прикрывает вход в верхнечелюстную пазуху."),
        s("processus_ethmoidalis", "process", "Processus ethmoidalis", "Решётчатый отросток",
          "Соединяется с крючковидным отростком решётчатой кости."),
    ],
    "vomer": [
        s("alae_vomeris", "process", "Alae vomeris", "Крылья сошника",
          "Охватывают клюв клиновидной кости.", side="paired"),
    ],
    "os_hyoideum": [
        s("corpus", "other", "Corpus ossis hyoidei", "Тело подъязычной кости", "Центральная часть."),
        s("cornu_majus", "process", "Cornu majus", "Большой рог", "Место прикрепления щитоподъязычной мембраны.",
          side="paired"),
        s("cornu_minus", "process", "Cornu minus", "Малый рог", "Место прикрепления шилоподъязычной связки.",
          side="paired"),
    ],
}

# Sutures (раздел 3.3) — modeled as free-standing structures, bone_id="cranium" (join line, not owned by one bone)
SUTURES = [
    s("sutura_coronalis", "suture", "Sutura coronalis", "Венечный шов",
      "Между лобной и теменными костями."),
    s("sutura_sagittalis", "suture", "Sutura sagittalis", "Сагиттальный шов",
      "Между теменными костями."),
    s("sutura_lambdoidea", "suture", "Sutura lambdoidea", "Ламбдовидный шов",
      "Между теменными и затылочной костями."),
    s("sutura_squamosa", "suture", "Sutura squamosa", "Чешуйчатый шов",
      "Между чешуёй височной кости и теменной костью.", side="paired"),
    s("sutura_sphenofrontalis", "suture", "Sutura sphenofrontalis", "Клиновидно-лобный шов",
      "Между большим крылом клиновидной кости и лобной костью.", side="paired"),
]

# ---------------------------------------------------------------------------

def build():
    bones = []
    for b in BONES:
        b = dict(b)
        b.setdefault("movable", False)
        b["mesh_ref"] = None
        bones.append(b)

    structures = []
    for bone_id, items in STRUCTURES_BY_BONE.items():
        for item in items:
            structures.append({
                "id": f"{bone_id}.{item['id_suffix']}",
                "bone_id": bone_id,
                "category": item["category"],
                "ta2_latin": item["ta2_latin"],
                "name_ru": item["name_ru"],
                "side": item["side"],
                "description": item["description"],
                "contents": item["contents"],
                "clinical_note": item["clinical_note"],
            })

    for item in SUTURES:
        structures.append({
            "id": f"cranium.{item['id_suffix']}",
            "bone_id": "cranium",
            "category": item["category"],
            "ta2_latin": item["ta2_latin"],
            "name_ru": item["name_ru"],
            "side": item["side"],
            "description": item["description"],
            "contents": item["contents"],
            "clinical_note": item["clinical_note"],
        })

    return {"bones": bones, "structures": structures}


def main():
    data = build()
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(data['bones'])} bones and {len(data['structures'])} structures to {OUT_PATH}")

    if "--validate" in sys.argv:
        try:
            import jsonschema
        except ImportError:
            print("jsonschema not installed, skipping validation (pip install jsonschema)")
            return
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.validate(instance=data, schema=schema)
        print("Validation OK against skull_metadata.schema.json")


if __name__ == "__main__":
    main()
