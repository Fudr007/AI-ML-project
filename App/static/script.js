function fetchRoster() {
    const url = document.getElementById('sofascore_url').value;
    const statusLabel = document.getElementById('fetch_status');

    if(!url) {
        statusLabel.innerText = "Put URL to the field!";
        statusLabel.style.color = "red";
        return;
    }

    statusLabel.innerText = "Dowloading from Sofascore API...";
    statusLabel.style.color = "blue";

    fetch('/fetch_roster', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ url: url })
    })
    .then(response => response.json())
    .then(data => {
        if(data.error) {
            statusLabel.innerText = data.error;
            statusLabel.style.color = "red";
        } else {
            document.querySelector('input[name="team_home"]').value = data.home_team;
            document.querySelector('input[name="team_away"]').value = data.away_team;

            document.querySelector('input[name="date"]').value = new Date(data.date * 1000).toISOString().split('T')[0];


            function fillSection(playerArray, containerId) {
                const container = document.getElementById(containerId);
                let inputs = container.querySelectorAll('input');

                while (inputs.length < playerArray.length) {
                    addField(containerId);
                    inputs = container.querySelectorAll('input');
                }

                playerArray.forEach((player, index) => {
                    inputs[index].value = player.name;
                });
            }

            const homeGKs = data.home_players.filter(p => p.position === 'G');
            const homePLs = data.home_players.filter(p => p.position !== 'G');

            fillSection(homeGKs, 'gk_home');
            fillSection(homePLs, 'pl_home');

            const awayGKs = data.away_players.filter(p => p.position === 'G');
            const awayPLs = data.away_players.filter(p => p.position !== 'G');

            fillSection(awayGKs, 'gk_away');
            fillSection(awayPLs, 'pl_away');

            statusLabel.innerText = "Roster downloaded and added successfully!";
            statusLabel.style.color = "green";
        }
    })
    .catch(error => {
        statusLabel.innerText = "Critical error: " + error;
        statusLabel.style.color = "red";
    });
}

function fetchPrevRooster(){
    const url_home = document.getElementById('sofascore_url_home').value;
    const url_away = document.getElementById('sofascore_url_away').value;

    const statusLabel = document.getElementById('fetch_status_prev');

    if(!url_home || !url_away) {
        statusLabel.innerText = "Put URLs to the field!";
        statusLabel.style.color = "red";
        return;
    }

    statusLabel.innerText = "Dowloading from Sofascore API...";
    statusLabel.style.color = "blue";

    fetch('/fetch_roster_prev', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ url_home: url_home, url_away: url_away })
    })
    .then(response => response.json())
    .then(data => {
        if(data.error) {
            statusLabel.innerText = data.error;
            statusLabel.style.color = "red";
        } else {
            document.querySelector('input[name="team_home"]').value = data.home_team;
            document.querySelector('input[name="team_away"]').value = data.away_team;

            function fillSection(playerArray, containerId) {
                const container = document.getElementById(containerId);
                let inputs = container.querySelectorAll('input');

                while (inputs.length < playerArray.length) {
                    addField(containerId);
                    inputs = container.querySelectorAll('input');
                }

                playerArray.forEach((player, index) => {
                    inputs[index].value = player.name;
                });
            }

            const homeGKs = data.home_players.filter(p => p.position === 'G');
            const homePLs = data.home_players.filter(p => p.position !== 'G');

            fillSection(homeGKs, 'gk_home');
            fillSection(homePLs, 'pl_home');

            const awayGKs = data.away_players.filter(p => p.position === 'G');
            const awayPLs = data.away_players.filter(p => p.position !== 'G');

            fillSection(awayGKs, 'gk_away');
            fillSection(awayPLs, 'pl_away');

            statusLabel.innerText = "Rosters downloaded and added successfully!";
            statusLabel.style.color = "green";
        }
    })
    .catch(error => {
        statusLabel.innerText = "Critical error: " + error;
        statusLabel.style.color = "red";
    });
}

function addField(type){
    const teamSuffix = type.includes('home') ? 'home' : 'away';

    const gkCount = document.querySelectorAll('#gk_' + teamSuffix + ' input').length;
    const plCount = document.querySelectorAll('#pl_' + teamSuffix + ' input').length;
    const totalPlayers = gkCount + plCount;

    if (totalPlayers >= 16) {
        alert("Roster is full! Highest number of players is 16.");
        return;
    }
    const field = document.createElement('input');
    field.required = true;
    field.type = "text";
    if (type.includes('gk')){
        field.name = type;
        field.placeholder = "Goalkeeper name"
    }else {
        field.name = type;
        field.placeholder = "Player name"
    }
    document.getElementById(type).appendChild(field);
}