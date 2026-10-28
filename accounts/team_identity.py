"""NFL team identity data used for favorite-team personalization and divisions."""

TEAM_DATA = {
    'ARI': {'name': 'Arizona Cardinals', 'division': 'NFC West', 'primary': '#97233F', 'secondary': '#000000', 'on_primary': '#FFFFFF'},
    'ATL': {'name': 'Atlanta Falcons', 'division': 'NFC South', 'primary': '#A71930', 'secondary': '#000000', 'on_primary': '#FFFFFF'},
    'BAL': {'name': 'Baltimore Ravens', 'division': 'AFC North', 'primary': '#241773', 'secondary': '#9E7C0C', 'on_primary': '#FFFFFF'},
    'BUF': {'name': 'Buffalo Bills', 'division': 'AFC East', 'primary': '#00338D', 'secondary': '#C60C30', 'on_primary': '#FFFFFF'},
    'CAR': {'name': 'Carolina Panthers', 'division': 'NFC South', 'primary': '#0085CA', 'secondary': '#101820', 'on_primary': '#FFFFFF'},
    'CHI': {'name': 'Chicago Bears', 'division': 'NFC North', 'primary': '#0B162A', 'secondary': '#C83803', 'on_primary': '#FFFFFF'},
    'CIN': {'name': 'Cincinnati Bengals', 'division': 'AFC North', 'primary': '#FB4F14', 'secondary': '#000000', 'on_primary': '#101820'},
    'CLE': {'name': 'Cleveland Browns', 'division': 'AFC North', 'primary': '#311D00', 'secondary': '#FF3C00', 'on_primary': '#FFFFFF'},
    'DAL': {'name': 'Dallas Cowboys', 'division': 'NFC East', 'primary': '#003594', 'secondary': '#869397', 'on_primary': '#FFFFFF'},
    'DEN': {'name': 'Denver Broncos', 'division': 'AFC West', 'primary': '#FB4F14', 'secondary': '#002244', 'on_primary': '#101820'},
    'DET': {'name': 'Detroit Lions', 'division': 'NFC North', 'primary': '#0076B6', 'secondary': '#B0B7BC', 'on_primary': '#FFFFFF'},
    'GB': {'name': 'Green Bay Packers', 'division': 'NFC North', 'primary': '#203731', 'secondary': '#FFB612', 'on_primary': '#FFFFFF'},
    'HOU': {'name': 'Houston Texans', 'division': 'AFC South', 'primary': '#03202F', 'secondary': '#A71930', 'on_primary': '#FFFFFF'},
    'IND': {'name': 'Indianapolis Colts', 'division': 'AFC South', 'primary': '#002C5F', 'secondary': '#A2AAAD', 'on_primary': '#FFFFFF'},
    'JAX': {'name': 'Jacksonville Jaguars', 'division': 'AFC South', 'primary': '#006778', 'secondary': '#D7A22A', 'on_primary': '#FFFFFF'},
    'KC': {'name': 'Kansas City Chiefs', 'division': 'AFC West', 'primary': '#E31837', 'secondary': '#FFB81C', 'on_primary': '#FFFFFF'},
    'LAC': {'name': 'Los Angeles Chargers', 'division': 'AFC West', 'primary': '#0080C6', 'secondary': '#FFC20E', 'on_primary': '#FFFFFF'},
    'LAR': {'name': 'Los Angeles Rams', 'division': 'NFC West', 'primary': '#003594', 'secondary': '#FFA300', 'on_primary': '#FFFFFF'},
    'LV': {'name': 'Las Vegas Raiders', 'division': 'AFC West', 'primary': '#000000', 'secondary': '#A5ACAF', 'on_primary': '#FFFFFF'},
    'MIA': {'name': 'Miami Dolphins', 'division': 'AFC East', 'primary': '#008E97', 'secondary': '#FC4C02', 'on_primary': '#FFFFFF'},
    'MIN': {'name': 'Minnesota Vikings', 'division': 'NFC North', 'primary': '#4F2683', 'secondary': '#FFC62F', 'on_primary': '#FFFFFF'},
    'NE': {'name': 'New England Patriots', 'division': 'AFC East', 'primary': '#002244', 'secondary': '#C60C30', 'on_primary': '#FFFFFF'},
    'NO': {'name': 'New Orleans Saints', 'division': 'NFC South', 'primary': '#101820', 'secondary': '#D3BC8D', 'on_primary': '#FFFFFF'},
    'NYG': {'name': 'New York Giants', 'division': 'NFC East', 'primary': '#0B2265', 'secondary': '#A71930', 'on_primary': '#FFFFFF'},
    'NYJ': {'name': 'New York Jets', 'division': 'AFC East', 'primary': '#125740', 'secondary': '#FFFFFF', 'on_primary': '#FFFFFF'},
    'PHI': {'name': 'Philadelphia Eagles', 'division': 'NFC East', 'primary': '#004C54', 'secondary': '#A5ACAF', 'on_primary': '#FFFFFF'},
    'PIT': {'name': 'Pittsburgh Steelers', 'division': 'AFC North', 'primary': '#101820', 'secondary': '#FFB612', 'on_primary': '#FFFFFF'},
    'SF': {'name': 'San Francisco 49ers', 'division': 'NFC West', 'primary': '#AA0000', 'secondary': '#B3995D', 'on_primary': '#FFFFFF'},
    'SEA': {'name': 'Seattle Seahawks', 'division': 'NFC West', 'primary': '#002244', 'secondary': '#69BE28', 'on_primary': '#FFFFFF'},
    'TB': {'name': 'Tampa Bay Buccaneers', 'division': 'NFC South', 'primary': '#D50A0A', 'secondary': '#34302B', 'on_primary': '#FFFFFF'},
    'TEN': {'name': 'Tennessee Titans', 'division': 'AFC South', 'primary': '#0C2340', 'secondary': '#4B92DB', 'on_primary': '#FFFFFF'},
    'WAS': {'name': 'Washington Commanders', 'division': 'NFC East', 'primary': '#5A1414', 'secondary': '#FFB612', 'on_primary': '#FFFFFF'},
}

TEAM_CHOICES = [('', 'Choose your favorite team')] + [
    (code, details['name']) for code, details in sorted(TEAM_DATA.items(), key=lambda item: item[1]['name'])
]


def team_division(team_code):
    return TEAM_DATA.get(team_code, {}).get('division', '')


def team_palette(team_code):
    return TEAM_DATA.get(team_code)
