"""seed 58 algerian wilayas

Revision ID: 002
Revises: 001
Create Date: 2026-07-03
"""
from collections.abc import Sequence

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WILAYAS_SQL = """
INSERT INTO wilayas (id, name_ar, name_fr, name_en, name_tz, latitude, longitude) VALUES
(1, 'أدرار', 'Adrar', 'Adrar', NULL, 27.87, -0.29),
(2, 'الشلف', 'Chlef', 'Chlef', NULL, 36.16, 1.33),
(3, 'الأغواط', 'Laghouat', 'Laghouat', NULL, 33.80, 2.88),
(4, 'أم البواقي', 'Oum El Bouaghi', 'Oum El Bouaghi', NULL, 35.87, 7.12),
(5, 'باتنة', 'Batna', 'Batna', NULL, 35.55, 6.17),
(6, 'بجاية', 'Béjaïa', 'Bejaia', NULL, 36.75, 5.06),
(7, 'بسكرة', 'Biskra', 'Biskra', NULL, 34.85, 5.73),
(8, 'بشار', 'Béchar', 'Bechar', NULL, 31.62, -2.22),
(9, 'البليدة', 'Blida', 'Blida', NULL, 36.47, 2.83),
(10, 'البويرة', 'Bouira', 'Bouira', NULL, 36.37, 3.90),
(11, 'تمنراست', 'Tamanrasset', 'Tamanrasset', NULL, 22.79, 5.52),
(12, 'تبسة', 'Tébessa', 'Tebessa', NULL, 35.40, 8.12),
(13, 'تلمسان', 'Tlemcen', 'Tlemcen', NULL, 34.88, -1.32),
(14, 'تيارت', 'Tiaret', 'Tiaret', NULL, 35.37, 1.32),
(15, 'تيزي وزو', 'Tizi Ouzou', 'Tizi Ouzou', NULL, 36.72, 4.05),
(16, 'الجزائر', 'Alger', 'Algiers', NULL, 36.75, 3.04),
(17, 'الجلفة', 'Djelfa', 'Djelfa', NULL, 34.67, 3.25),
(18, 'جيجل', 'Jijel', 'Jijel', NULL, 36.82, 5.77),
(19, 'سطيف', 'Sétif', 'Setif', NULL, 36.19, 5.41),
(20, 'سعيدة', 'Saïda', 'Saida', NULL, 34.83, 0.15),
(21, 'سكيكدة', 'Skikda', 'Skikda', NULL, 36.87, 6.91),
(22, 'سيدي بلعباس', 'Sidi Bel Abbès', 'Sidi Bel Abbes', NULL, 35.19, -0.63),
(23, 'عنابة', 'Annaba', 'Annaba', NULL, 36.90, 7.77),
(24, 'قالمة', 'Guelma', 'Guelma', NULL, 36.46, 7.43),
(25, 'قسنطينة', 'Constantine', 'Constantine', NULL, 36.37, 6.61),
(26, 'المدية', 'Médéa', 'Medea', NULL, 36.27, 2.75),
(27, 'مستغانم', 'Mostaganem', 'Mostaganem', NULL, 35.93, 0.09),
(28, 'مسيلة', 'M''Sila', 'Msila', NULL, 35.70, 4.55),
(29, 'معسكر', 'Mascara', 'Mascara', NULL, 35.40, 0.14),
(30, 'ورقلة', 'Ouargla', 'Ouargla', NULL, 31.96, 5.33),
(31, 'وهران', 'Oran', 'Oran', NULL, 35.70, -0.65),
(32, 'البيض', 'El Bayadh', 'El Bayadh', NULL, 32.76, 1.02),
(33, 'إليزي', 'Illizi', 'Illizi', NULL, 26.51, 8.48),
(34, 'برج بوعريريج', 'Bordj Bou Arréridj', 'Bordj Bou Arreridj', NULL, 36.07, 4.76),
(35, 'بومرداس', 'Boumerdès', 'Boumerdes', NULL, 36.76, 3.48),
(36, 'الطارف', 'El Tarf', 'El Tarf', NULL, 36.77, 8.31),
(37, 'تندوف', 'Tindouf', 'Tindouf', NULL, 27.67, -8.13),
(38, 'تيسمسيلت', 'Tissemsilt', 'Tissemsilt', NULL, 35.61, 1.81),
(39, 'الوادي', 'El Oued', 'El Oued', NULL, 33.37, 6.86),
(40, 'خنشلة', 'Khenchela', 'Khenchela', NULL, 35.43, 7.14),
(41, 'سوق أهراس', 'Souk Ahras', 'Souk Ahras', NULL, 36.29, 7.95),
(42, 'تيبازة', 'Tipaza', 'Tipaza', NULL, 36.59, 2.45),
(43, 'ميلة', 'Mila', 'Mila', NULL, 36.45, 6.26),
(44, 'عين الدفلى', 'Aïn Defla', 'Ain Defla', NULL, 36.26, 1.97),
(45, 'النعامة', 'Naâma', 'Naama', NULL, 33.27, -0.31),
(46, 'عين تموشنت', 'Aïn Témouchent', 'Ain Temouchent', NULL, 35.30, -1.14),
(47, 'غرداية', 'Ghardaïa', 'Ghardaia', NULL, 32.49, 3.67),
(48, 'غليزان', 'Relizane', 'Relizane', NULL, 35.74, 0.56),
(49, 'تيميمون', 'Timimoun', 'Timimoun', NULL, 29.26, 0.23),
(50, 'بني عباس', 'Béni Abbès', 'Beni Abbes', NULL, 30.08, -2.16),
(51, 'عين صالح', 'Aïn Salah', 'Ain Salah', NULL, 27.19, 2.46),
(52, 'عين قزام', 'Aïn Guezzam', 'Ain Guezzam', NULL, 19.57, 5.77),
(53, 'تقرت', 'Touggourt', 'Touggourt', NULL, 33.11, 6.06),
(54, 'جانت', 'Djanet', 'Djanet', NULL, 24.55, 9.48),
(55, 'المغير', 'El M''Ghair', 'El M''Ghair', NULL, 33.95, 5.92),
(56, 'المنيعة', 'El Meniaa', 'El Menia', NULL, 30.58, 2.88),
(57, 'أولاد جلال', 'Ouled Djellal', 'Ouled Djellal', NULL, 34.43, 5.07),
(58, 'برج باجي مختار', 'Bordj Badji Mokhtar', 'Bordj Badji Mokhtar', NULL, 21.33, 0.95)
ON CONFLICT (id) DO NOTHING;
"""


def upgrade() -> None:
    op.execute(WILAYAS_SQL)


def downgrade() -> None:
    op.execute("DELETE FROM wilayas")
