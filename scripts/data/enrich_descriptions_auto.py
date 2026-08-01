#!/usr/bin/env python3
"""Auto-generate destination descriptions for wilayas missing Wikivoyage content."""

import psycopg2

DB_CONFIG = {
    "host": "localhost", "port": 5434,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

# Region groupings for narrative
REGION_GROUPS = {
    "Sahara": {"Tamanrasset", "Adrar", "Illizi", "Tindouf", "Ouargla", "El Oued",
               "Touggourt", "Djanet", "Timimoun", "Béni Abbès", "Aïn Salah",
               "Aïn Guezzam", "El Meniaa", "Bordj Badji Mokhtar", "El M'Ghair",
               "Ghardaïa", "Biskra", "Béchar", "Laghouat", "El Bayadh", "Naâma"},
    "Kabylie": {"Tizi Ouzou", "Béjaïa", "Bouira", "Boumerdès"},
    "Aurès": {"Batna", "Khenchela", "Oum El Bouaghi", "Tébessa", "Souk Ahras"},
    "Tell": {"Alger", "Oran", "Annaba", "Constantine", "Blida", "Tipaza",
             "Mostaganem", "Skikda", "Jijel", "Chlef", "Aïn Defla", "Médéa",
             "Tissemsilt", "Mila", "Guelma", "El Tarf", "Béjaïa", "Sétif",
             "Boumerdès", "Tizi Ouzou", "Bouira", "Relizane", "Mascara",
             "Saïda", "Aïn Témouchent", "Sidi Bel Abbès"},
    "Hauts Plateaux": {"Tiaret", "Djelfa", "M'Sila", "Bordj Bou Arréridj",
                        "Sétif", "Saïda", "Mascara", "Relizane", "Tissemsilt",
                        "Khenchela", "Barika", "Ouled Djellal"},
}

WILAYA_DESCRIPTIONS = {
    "Adrar": "Adrar est le cœur du Touat, une oasis historique du Sahara algérien. Cette région désertique est célèbre pour ses ksour (villages fortifiés), ses palmeraies et ses foggaras (systèmes d'irrigation ancestraux).",
    "Chlef": "Chlef se situe dans la plaine du Chelif, au nord-ouest de l'Algérie. La région est connue pour ses riches terres agricoles et les thermes de la Fontaine Chaude, source d'eau chaude naturelle réputée.",
    "Laghouat": "Laghouat est la porte du Sahara, célèbre pour son Kheneg (gorge) et sa palmeraie. La ville oasienne est un carrefour entre le nord et le grand sud algérien.",
    "Oum El Bouaghi": "Oum El Bouaghi se situe dans la région des Aurès orientaux. Cette région agricole est entourée de montagnes et de plaines fertiles.",
    "Béchar": "Béchar est la capitale de la Saoura, région désertique du sud-ouest algérien. La ville est la porte du Sahara occidental, célèbre pour ses paysages de hamada et d'oasis.",
    "Médéa": "Médéa est une ville des hauts plateaux algériens, nichée dans l'Atlas tellien. Elle est réputée pour son climat tempéré et ses sources d'eau naturelle.",
    "Mostaganem": "Mostaganem est une ville côtière de l'ouest algérien, baignée par la mer Méditerranée. Son front de mer, sa corniche et ses plages en font une destination balnéaire prisée.",
    "M'Sila": "M'Sila se situe dans les hauts plateaux algériens, entre la chaîne du Hodna et les monts du Zab. La région est un carrefour agricole et pastoral important.",
    "Mascara": "Mascara est une ville historique de l'ouest algérien, nichée dans les monts du Dahra. Berceau de l'émir Abdelkader, elle possède un riche patrimoine historique.",
    "Illizi": "Illizi est la porte du Tassili n'Ajjer, l'un des plus grands parcs nationaux d'Afrique. Cette région du sud-est algérien abrite des gravures rupestres préhistoriques classées à l'UNESCO.",
    "Bordj Bou Arréridj": "Bordj Bou Arréridj est une ville des hauts plateaux algériens, connue pour son artisanat traditionnel, notamment la tapisserie et la poterie.",
    "Boumerdès": "Boumerdès s'étend le long de la côte méditerranéenne à l'est d'Alger. Ses plages, ses forêts et le Cap Djinet en font une destination de week-end prisée des Algérois.",
    "El Tarf": "El Tarf abrite le Parc National d'El Kala, une réserve de biosphère UNESCO. La région est l'une des plus riches d'Algérie en biodiversité, avec ses lacs, forêts et plages méditerranéennes.",
    "Tindouf": "Tindouf est la ville la plus isolée du sud-ouest algérien, aux portes du Sahara occidental. La région est célèbre pour la hamada du Draa et les gisements de Gara Djebilet.",
    "Tissemsilt": "Tissemsilt se situe dans les monts de l'Ouarsenis. La région est réputée pour ses paysages montagneux, ses forêts et ses barrages.",
    "El Oued": "El Oued est la capitale du Souf, une région d'oasis unique au Sahara algérien. Célèbre pour ses milliers de palmeraies en creux (ghout), elle est surnommée la ville aux mille coupoles.",
    "Souk Ahras": "Souk Ahras est une ville des Aurès orientaux, berceau de l'écrivain Kateb Yacine. La région est riche en sites archéologiques numides et romains, dont Tiffech et Madaure.",
    "Mila": "Mila se situe dans le nord-est algérien, sur les hauteurs des gorges de l'Oued Rhummel. Le site archéologique de Milev témoigne de son passé romain.",
    "Aïn Defla": "Aïn Defla s'étend dans la vallée du Chelif, entre l'Atlas tellien et l'Atlas saharien. La région est réputée pour ses sources thermales et ses montagnes de l'Ouarsenis.",
    "Relizane": "Relizane est une ville de l'ouest algérien, dans la plaine du Chelif. La région est un important centre agricole, notamment pour la céréaliculture et l'oléiculture.",
    "Timimoun": "Timimoun est une oasis du Gourara, une région du Sahara central. La ville est célèbre pour ses oasis, ses palmeraies et l'art de ses tapis traditionnels.",
    "Béni Abbès": "Béni Abbès est une oasis de la vallée de la Saoura, dans le Sahara algérien. Surnommée la perle du Sahara, elle est réputée pour son patrimoine architectural en terre crue.",
    "Aïn Salah": "Aïn Salah est une oasis du Sahara central, ancienne étape caravanière entre le nord et l'Afrique subsaharienne. La région est célèbre pour ses foggaras, systèmes d'irrigation souterrains.",
    "Aïn Guezzam": "Aïn Guezzam est la porte du Ténéré algérien, à la frontière du Niger. C'est la porte sud du Sahara algérien, point de départ vers les immensités désertiques.",
    "Touggourt": "Touggourt est une oasis du Bas-Sahara algérien, capitale de l'Oued Righ. La région est célèbre pour ses palmeraies, ses oueds et son architecture traditionnelle.",
    "Djanet": "Djanet est le joyau du Tassili n'Ajjer, au sud-est de l'Algérie. La région est un musée à ciel ouvert d'art rupestre préhistorique classé à l'UNESCO.",
    "El M'Ghair": "El M'Ghair est une oasis du Bas-Sahara, dans la région de l'Oued Righ. La région est réputée pour ses palmeraies et la culture des dattes Deglet Nour.",
    "El Meniaa": "El Meniaa est une oasis du Sahara central, au cœur du Grand Erg Occidental. La région est un carrefour entre le nord et le sud de l'Algérie.",
    "Ouled Djellal": "Ouled Djellal se situe dans la région des Zibans, au sud des Aurès. La région est réputée pour ses palmeraies et ses vastes étendues steppiques.",
    "Bordj Badji Mokhtar": "Bordj Badji Mokhtar est le poste frontière sud de l'Algérie, au cœur du désert du Ténéré. C'est l'une des portes de l'Afrique subsaharienne.",
    "Aflou": "Aflou est une ville des monts de l'Atlas saharien, dans la région de Laghouat. La région est réputée pour ses forêts de cèdres et ses pâturages d'altitude.",
    "El Abiodh Sidi Cheikh": "El Abiodh Sidi Cheikh se situe à la lisière du Sahara, dans les monts des Ksour. La région est riche en oasis et en ksour traditionnels.",
    "El Aricha": "El Aricha est une ville steppique aux confins ouest de l'Algérie, près de la frontière marocaine.",
    "El Kantara": "El Kantara est la porte du désert, une gorge spectaculaire entre les monts des Aurès et le Sahara. Le site est célèbre pour ses palmeraies et son pont romain.",
    "Barika": "Barika est une ville des hauts plateaux algériens, dans la wilaya de Batna. La région est un centre agricole important.",
    "Bou Saâda": "Bou Saâda est une ville oasis au pied du mont Kerdada, à la lisière du Sahara. Surnommée la porte du désert, elle est réputée pour son art et son artisanat.",
    "Bir El Ater": "Bir El Ater se situe dans l'est algérien, près de la frontière tunisienne. La région est riche en gisements de phosphates.",
    "Ksar El Boukhari": "Ksar El Boukhari est une ville des hauts plateaux, dans la région de Médéa.",
    "Ksar Chellala": "Ksar Chellala est une ville des hauts plateaux algériens, réputée pour ses tapis traditionnels tissés à la main.",
    "Aïn Oussera": "Aïn Oussera est une ville des hauts plateaux, dans la wilaya de Djelfa. C'est un carrefour important entre le nord et le sud.",
    "Messaad": "Messaad est une ville des hauts plateaux, dans la wilaya de Djelfa, à la lisière du Sahara.",
    "Naâma": "Naâma se situe dans les monts des Ksour, à l'ouest de l'Algérie. La région est réputée pour ses paysages steppiques et ses oasis de montagne.",
    "Aïn Témouchent": "Aïn Témouchent est une ville de l'ouest algérien, proche de la côte méditerranéenne. La région est réputée pour sa production viticole et ses plages.",
    "Tiaret": "Tiaret est une ville des hauts plateaux de l'ouest algérien. La région est réputée pour son élevage équin (pur-sang arabe) et son patrimoine historique.",
    "Saïda": "Saïda est une ville des hauts plateaux de l'ouest algérien, nichée dans les monts des Dhaya. La région est réputée pour ses forêts de pins d'Alep.",
    "Sidi Bel Abbès": "Sidi Bel Abbès est une ville de l'ouest algérien, capitale des hauts plateaux. Ancien centre de la Légion étrangère française, elle possède un riche passé militaire.",
    "Guelma": "Guelma est une ville du nord-est algérien, réputée pour ses sources thermales de Hammam Debagh et son théâtre romain antique.",
    "Tébessa": "Tébessa est une ville de l'est algérien, célèbre pour son patrimoine romain exceptionnel : l'Arc de Caracalla, le Temple de Minerve et ses murailles byzantines.",
    "Jijel": "Jijel est une ville côtière du nord-est algérien, baignée par la mer Méditerranée. Ses plages magnifiques, le Cap Cavallo et le Parc National de Taza en font une destination balnéaire et naturelle de premier plan.",
    "El Bayadh": "El Bayadh est une ville des hauts plateaux de l'ouest algérien, à la lisière du Sahara. La région est réputée pour ses vastes étendues steppiques, ses monts des Ksour et son élevage ovin.",
    "Khenchela": "Khenchela est une ville des monts des Aurès, dans le nord-est algérien. La région est réputée pour ses paysages montagneux, ses sources d'eau naturelle, son lac et sa forêt dense de cèdres.",
    "Tipaza": "Tipaza est une ville côtière à l'ouest d'Alger, célèbre pour ses ruines romaines classées à l'UNESCO. Le Tombeau de la Chrétienne, le Parc National de Chenoua et ses plages en font une destination incontournable.",
    "Tlemcen": "Tlemcen est une ville historique de l'ouest algérien, capitale de la civilisation zianide. Son riche patrimoine architectural (Mosquée de Sidi Boumediene, Palais El Mechouar), ses cascades d'Oureï et son parc national en font une destination culturelle et naturelle majeure.",
    "Tizi Ouzou": "Tizi Ouzou est la capitale de la Grande Kabylie, au cœur du massif du Djurdjura. La région est réputée pour ses paysages montagneux spectaculaires, ses villages perchés, son artisanat traditionnel et le Parc National du Djurdjura.",
    "Djelfa": "Djelfa est une ville des hauts plateaux algériens, à la porte du Sahara. La région est célèbre pour son rocher de sel, ses steppes et ses dolmens préhistoriques.",
    "Ouargla": "Ouargla est une oasis du Sahara algérien, capitale du Bas-Sahara. La région est célèbre pour ses palmeraies, ses ksour traditionnels et la culture des dattes.",
}


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    print("=== Auto-generated Destination Descriptions ===\n")

    # Get all wilayas without a FR description
    cur.execute("SELECT id, name_fr FROM wilayas WHERE description IS NULL OR description = ''")
    missing = cur.fetchall()
    print(f"Wilayas missing descriptions: {len(missing)}")

    n_fr = 0
    n_en = 0

    for wid, name_fr in missing:
        desc = WILAYA_DESCRIPTIONS.get(name_fr)
        if desc:
            cur.execute("UPDATE wilayas SET description = %s WHERE id = %s", (desc, wid))
            n_fr += 1
            print(f"  [{wid:2d}] {name_fr}: ✓")

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM wilayas WHERE description IS NOT NULL AND description != ''")
    total = cur.fetchone()[0]
    conn.close()

    print(f"\nAuto-generated: {n_fr} FR descriptions")
    print(f"Total with descriptions: {total} / 69")


if __name__ == "__main__":
    main()
