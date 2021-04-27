socket =  io()

function byId(name) {
	return document.getElementById(name)
}

function echo(x) {console.log(x)}

function getNotes() {
	socket.emit("get_notes", "", "", "")
}

function getNote(id) {
    socket.emit("get_note", id)
}

function displayNote(n) {
    var main = byId("main")
    main.innerHTML = n
}

function updateNotesView(notes) {
	var view = byId("notes")
	while(view.options.length > 0) view.remove(0)

	for(var [id, title] of notes) {
		var opt = document.createElement("option")
		opt.value = id
		opt.text = title
		view.add(opt)
	}
}

socket.on('connect', function (event) {
	getNotes()
});

socket.on('notes', function (notes){
	updateNotesView(notes)
})

socket.on('note', function (note) {
    displayNote(note)
});

document.addEventListener("DOMContentLoaded", function(){
    byId("notes").addEventListener("change", function(){
        getNote(this.options[this.selectedIndex].value)
    })
});
