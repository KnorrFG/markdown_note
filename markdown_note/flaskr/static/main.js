/* The whole thing works like this: if you run mdn serve, a webserver is
 * started via flask. On the / route, it returns the index page, which is a
 * very simple Single page application, which loads socket.io.js and this file.
 * When the user enters a pattern, or klicks a note, the server is informed,
 * and will send back the requested information (either a list of notes
 * matching the serach patterns, or the content of the note that was clicked).
 * However, this happens asynchroniously, i.e. these notifier functions
 * (getNote and getNotes) dont have return values. Instead there are listeners
 * defined on the socket, that are executed, when the server sends the
 * requested information. That is what the socket.on listeners are.
 * finally, the last block attaches the js behavior to the html elements.
 * */
socket =  io()

function byId(name) {
	return document.getElementById(name)
}

function echo(x) {console.log(x)}

function getNotes(pattern, group, tags) {
	socket.emit("get_notes", pattern, group, tags)
}

function getNote(id) {
    socket.emit("get_note", id)
}

function displayNote(n) {
    var main = byId("content")
    main.innerHTML = n
}

function updateNotesView(notes) {
	var view = byId("notes")
	while(view.options.length > 0) view.remove(0)

	for(var [id, title] of notes) {
		var opt = document.createElement("option")
		opt.value = id
		opt.text = title + " (" + id + ")"
		view.add(opt)
	}
}

socket.on('connect', function (event) {
	getNotes("", "", "")
});

socket.on('notes', function (notes){
	updateNotesView(notes)
})

socket.on('note', function (note) {
    displayNote(note)
});

function valById(id) {
    return byId(id).value
}

function searchPt() {
    return valById("search_pattern")
}

function groupPt() {
    return valById("group_pattern")
}

function tagPt() {
    return valById("tag_pattern")
}

document.addEventListener("DOMContentLoaded", function(){
    byId("notes").addEventListener("change", function(){
        getNote(this.options[this.selectedIndex].value)
    })

    byId("search_pattern").addEventListener("input", function() {
        getNotes(this.value, groupPt(), tagPt())
    })

    byId("group_pattern").addEventListener("input", function() {
        getNotes(searchPt(), this.value, tagPt())
    })
    
    byId("tag_pattern").addEventListener("input", function() {
        getNotes(searchPt(), groupPt(), this.value)
    })
});
