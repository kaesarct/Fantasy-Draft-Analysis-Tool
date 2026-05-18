let currentTaskId = null;
let pollInterval = null;

// I file .js statici non sono processati dal template engine di Django,
// quindi leggiamo il CSRF token dal cookie impostato automaticamente da Django.
function getCsrfToken() {
    const name = 'csrftoken';
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [key, value] = cookie.trim().split('=');
        if (key === name) return decodeURIComponent(value);
    }
    return '';
}

function startTask(actionName) {
    if (pollInterval) {
        alert("C'è già un task in esecuzione. Attendi il termine.");
        return;
    }
    
    document.getElementById('progress-container').style.display = 'block';
    document.getElementById('progress-bar').style.width = '0%';
    document.getElementById('progress-bar').style.backgroundColor = 'var(--default-button-bg, #417690)';
    document.getElementById('progress-text').innerText = "Inizializzazione ambiente...";
    
    const formData = new FormData();
    formData.append('action', actionName);
    formData.append('csrfmiddlewaretoken', getCsrfToken());
    
    fetch('', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'ok') {
            currentTaskId = data.task_id;
            pollInterval = setInterval(checkStatus, 1500);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert("Errore di rete durante l'avvio.");
    });
}

function startPreastaTask() {
    if (pollInterval) {
        alert("C'è già un task in esecuzione. Attendi il termine.");
        return;
    }
    
    const fileInput = document.getElementById('preasta_file');
    if (!fileInput.files.length) {
        alert("Devi prima selezionare un file Excel da caricare!");
        return;
    }
    
    const seasonId = document.getElementById('preasta_season_id').value;
    
    document.getElementById('progress-container').style.display = 'block';
    document.getElementById('progress-bar').style.width = '0%';
    document.getElementById('progress-bar').style.backgroundColor = '#9c27b0';
    document.getElementById('progress-text').innerText = "Caricamento file e inizializzazione...";
    
    const formData = new FormData();
    formData.append('action', 'import_preasta');
    formData.append('season_id', seasonId);
    formData.append('file', fileInput.files[0]);
    formData.append('csrfmiddlewaretoken', getCsrfToken());
    console.log(formData);
    fetch('', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'ok') {
            currentTaskId = data.task_id;
            pollInterval = setInterval(checkStatus, 1500);
        } else {
            alert(data.message || "Errore sconosciuto durante l'upload");
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert("Errore di rete durante l'avvio.");
    });
}

function checkStatus() {
    if (!currentTaskId) return;
    
    fetch('/admin/import-dashboard/task/' + currentTaskId + '/')
    .then(response => response.json())
    .then(data => {
        if (data.status === 'NOT_FOUND') return;
        
        let percentage = 0;
        if (data.total > 0) {
            percentage = Math.round((data.processed / data.total) * 100);
        } else if (data.status === 'COMPLETED') {
            percentage = 100;
        }
        
        document.getElementById('progress-bar').style.width = percentage + '%';
        document.getElementById('progress-text').innerText = `Stato: ${data.status_display} - Completati ${data.processed} su ${data.total} (${percentage}%)`;
        
        if (data.status === 'COMPLETED' || data.status === 'ERROR') {
            clearInterval(pollInterval);
            pollInterval = null;
            if (data.status === 'ERROR') {
                document.getElementById('progress-text').innerText += " - ERRORE: " + data.error;
                document.getElementById('progress-bar').style.backgroundColor = '#f44336';
            } else {
                document.getElementById('progress-bar').style.backgroundColor = '#4caf50';
            }
            setTimeout(() => location.reload(), 2500);
        }
    });
}

function deleteDatabase() {
    if(confirm("ATTENZIONE! Sei sicuro di voler cancellare TUTTI i calciatori, le squadre e i voti dal database? Questa azione non può essere annullata.")) {
        if(confirm("Sei veramente sicuro? (Ultimo avviso)")) {
            const formData = new FormData();
            formData.append('action', 'delete_all_data');
            formData.append('csrfmiddlewaretoken', getCsrfToken());
            
            fetch('', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'deleted') {
                    alert("Database svuotato con successo!");
                    location.reload();
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert("Errore durante la cancellazione.");
            });
        }
    }
}

function clearPreasta() {
    if(confirm("Sei sicuro di voler svuotare i dati della tua analisi Pre-Asta?")) {
        const formData = new FormData();
        formData.append('action', 'clear_preasta');
        formData.append('csrfmiddlewaretoken', getCsrfToken());
        
        fetch('', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'deleted') {
                alert(data.message || "Pre-asta svuotata con successo!");
                location.reload();
            } else {
                alert("Errore: " + (data.message || "Sconosciuto"));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert("Errore di rete durante lo svuotamento.");
        });
    }
}