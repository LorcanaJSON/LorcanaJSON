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
	"Q3": {
		"243/204": {
			"Sven - Leaping Reindeer": ("11", "243/204"),
			"Mr. Incredible - Super Strong": ("12", "243/204")
		},
		"246/207": {
			"Christopher Robin - Hunny Sage": ("13", "246/207")
		},
		"247/207": {
			"Violet Parr - Super Resilient": ("13", "247/207")
		},
		"16/PD1": {
			"With a Few Good Friends": ("Promos", "16/PD1")
		},
		"17/PD1": {
			"The Beanstalk - Onward and Upward": ("Promos", "17/PD1")
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
}
TCGPLAYER_ID_ADDITIONS: Dict[str, int] = {
	"42/P3": 683651,
	"9/PD1": 722990,
	"10/PD1": 722992,
	"11/PD1": 722993,
	"12/PD1": 722994,
	"13/PD1": 722995,
	"14/PD1": 722996,
	"1/RPH": 722997,
	"2/RPH": 722998,
	"3/RPH": 722999,
	"4/RPH": 723000,
	"5/RPH": 723002,
}
