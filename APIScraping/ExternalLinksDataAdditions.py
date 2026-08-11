from typing import Dict


CORRECTIONS = {
	"Promos": {
		"1": {
			"Dragon Fire": ("Promos", "1/C1")
		},
		"2": {
			"Let It Go": ("Promos", "2/C1")
		},
		"3": {
			"Cinderella - Stouthearted": ("Promos", "3/C1")
		},
		"4": {
			"Rapunzel - Gifted with Healing": ("Promos", "4/C1")
		},
		"5": {
			"Mickey Mouse - Brave Little Tailor": ("Promos", "5/C1")
		},
		"6": {
			"Invited to the Ball": ("Promos", "6/C1")
		},
		"7": {
			"Elsa's Ice Palace - Place of Solitude": ("Promos", "7/C1")
		},
		"8": {
			"Kuzco - Temperamental Emperor": ("Promos", "8/C1")
		},
		"9": {
			"Baymax - Armored Companion": ("Promos", "9/C1")
		},
		"10": {
			"A Whole New World": ("Promos", "10/C1")
		},
		"11/P": {
			"Mickey Mouse - Musketeer": ("Promos", "11/P1")
		},
		"12/P1": {
			"The Queen - Mirror Seeker": ("Promos", "12/P3")
		},
		"24/P2": {
			"Hiro Hamada - Armor Designer": ("Promos", "24A/P2")
		}
	},
	"Q1": {
		"11": {
			"The Hexwell Crown": ("Q1", "29")
		},
		"223/204": {
			"Piglet - Pooh Pirate Captain": ("3", "223/204"),
			"Yen Sid - Powerful Sorcerer": ("4", "223/204")
		},
		"224/204": {
			"Mulan - Elite Archer": ("4", "224/204")
		},
		"225/204": {
			"Mickey Mouse - Playful Sorcerer": ("4", "225/204")
		}
	},
	"Q2": {
		"223/204": {
			"Bolt - Superdog": ("7", "223/204"),
			"Goofy - Groundbreaking Chef": ("8", "223/204")
		},
		"224/204": {
			"Elsa - Ice Maker": ("7", "224/204"),
			"Pinocchio - Strings Attached": ("8", "224/204")
		}
	},
	"8": {
		"154": {
			"Olaf - Recapping the Story": ("8", "156/204")
		}
	},
	"9": {
		"41": {
			"Jafar - Lamp Thief": ("9", "59/204")
		}
	},
	"12": {
		"400": {
			"Doc - Taking Notes": ("12", "40/204")
		},
		"480": {
			"Violet Parr - Learning New Powers": ("12", "48/204")
		}
	}
}

# Sometimes some values just aren't in the input data, so manually add them here
CARDMARKET_ID_ADDITIONS: Dict[str, int] = {
	"27/P2": 826584,
	"28/P2": 826585,
	"29/P2": 826586,
	"30/P2": 826587,
	"31/P2": 826588,
	"32/P2": 826589,
	"33/P2": 826590,
	"35/P2": 826591,
	"1/PD1": 898820,
	"2/PD1": 898818,
}
TCGPLAYER_ID_ADDITIONS: Dict[str, int] = {
	"10/C1": 654595,
	"2/C2": 672472,
	"4/C2": 695330,
	"5/C2": 686340,
	"7/C2": 672467,
	"9/C2": 693401,
	"10/C2": 544501,
	"1/CC1": 702517,
	"2/CC1": 702518,
	"3/CC1": 702519,
	"4/CC1": 702520,
	"5/CC1": 702521,
	"6/CC1": 702603,
	"16/D23": 679565,
	"23/P3": 661794,
	"24/P3": 662883,
	"27/P3": 662256,
	"28/P3": 673344,
	"29/P3": 673347,
	"30/P3": 673351,
	"31/P3": 673338,
	"32/P3": 673342,
	"33/P3": 673334,
	"34/P3": 673333,
	"35/P3": 673336,
	"36/P3": 683650,
	"39/P3": 678645,
	"42/P3": 683651,
	"43/P3": 692413,
	"44/P3": 692476,
	"45/P3": 692477,
	"46/P3": 692478,
	"47/P3": 692479,
	"48/P3": 692480,
	"49/P3": 692481,
	"50/P3": 692482,
	"51/P3": 692483,
	"52/P3": 692484,
	"53/P3": 692485,
	"54/P3": 692486,
	"55/P3": 692487,
	"3/PD1": 705068,
	"4/PD1": 705072,
	"5/PD1": 705073,
	"6/PD1": 702706,
	"7/PD1": 705074,
	"8/PD1": 702707,
}
