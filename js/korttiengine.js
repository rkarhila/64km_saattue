
var siirra_seuraavaan = function(el, i){
    console.log('from',el);
    console.log('to', el.parentElement.children[i]);
    el.parentElement.parentElement.children[i].appendChild(el);
    if (i < 3) {
	el.setAttribute( "onClick", "javascript: siirra_seuraavaan(this,"+(i+1)+");" );
    } else
    {
	el.setAttribute( "onClick", "" );
    }
}

var siirra_aseapupoydalle = function(el, i){
    console.log('from',el);
    console.log('to', el.parentElement.children[i]);
    el.parentElement.parentElement.children[i].appendChild(el);
    if (i < 3) {
	el.setAttribute( "onClick", "javascript: siirra_yohyokkayksiin(this,"+(i+1)+");" );
    } else
    {
	el.setAttribute( "onClick", "" );
    }
}


var nayta_yohyokkays = function(el,elid) {
    el.classList.add('kortin_vaklaus');
    el.classList.add("yohyokkays_nakyva");
    el.setAttribute( "onClick", "javascript: siirra_seuraavaan(this,2);" );
    setTimeout(function() {
	console.log(el);
	if (el.classList.contains("yohyokkays_nakyva")) {
	    el.classList.remove("kortin_vaklaus");
	    el.classList.remove("yohyokkays_nakyva");
	    el.setAttribute( "onClick", "javascript: nayta_yohyokkays(this);" );
	}
    }, 3000)
}


var siirra_yohyokkayksiin = function(el){
    console.log('from',el);
    el.classList.add('kortti');
    el.classList.remove("yohyokkays_nakyva");
    pakka = document.querySelector("#yohyokkayspakka");

    randomposition = Math.floor(Math.random() * pakka.children.length)
    if ( randomposition == pakka.children.length1-1) {
	console.log('Appending aseapu at position ' + randomposition);
	pakka.appendChild(el);
    }
    else {
	console.log('Inserting aseapu before position ' + (randomposition+1));
	pakka.insertBefore(el, pakka.children[randomposition+1] )
    }
    el.setAttribute( "onClick", "javascript: nayta_yohyokkays(this);" );
    
    // sekoita yohyokkays:
    //for (var i = pakka.children.length; i >= 0; i--) {
    //	pakka.appendChild(ul.children[Math.random() * i | 0]);
    //}
}




// Piirretaan!

var piirra_korruptiokortti = function(data) {
    const kortti = document.createElement("div");
    kortti.classList.add('kortti');
    kortti.innerHTML = data.id;
    kortti.innerHTML += '<h4>'+data.mita+"</h4>";
    kortti.innerHTML += '<p>'+data.paljonko+"</p>";

    kortti.setAttribute( "onClick", "javascript: siirra_seuraavaan(this,2);" );
    return kortti;
}


var piirra_vastarintakortti = function(data) {
    const kortti = document.createElement("div");
    kortti.classList.add('kortti');
    kortti.innerHTML = data.id;
    kortti.innerHTML += '<h4>'+data.maasto+"</h4>";
    kortti.innerHTML += '<p>Kesto:'+data.kesto+"</p>";
    kortti.innerHTML += '<p>Hyökkäys: Jos <b>'+data.Jos+":</b> "+data.niin+"</p>";
    kortti.innerHTML += '<p>Muuten:'+data.muuten+"</br>";

    kortti.innerHTML += '<p>Ryöstettävää:'+data.ryostettavaa+"</br>";

    kortti.setAttribute( "onClick", "javascript: siirra_seuraavaan(this,2);" );
    return kortti;
}

var piirra_ryostokortti = function(data) {
    const kortti = document.createElement("div");
    kortti.classList.add('kortti');
    kortti.innerHTML = data.id;
    kortti.innerHTML += '<h4>'+data.paikka+"</h4>";
    kortti.innerHTML += '<p>Jos <b>'+data.Jos+":</b> "+data.niin+"</p>";
    kortti.innerHTML += '<p>Muuten:'+data.muulloin+"</br>";


    kortti.setAttribute( "onClick", "javascript: siirra_seuraavaan(this,2);" );
    return kortti;
}

var piirra_yohyokkayskortti = function(data) {
    const kortti = document.createElement("div");
    kortti.classList.add('kortti');
    kortti.innerHTML = data.id;
    kortti.innerHTML += '<h4>'+data.nimi+"</h4>";
    if (data.erikois == '') {
	kortti.innerHTML += '<p>Kohde:'+data.kohde+"</p>";
	kortti.innerHTML += '<p>Hyökkäys: Jos <b>'+data.jos+":</b> "+data.niin+"</p>";
	kortti.innerHTML += '<p>Muuten:'+data.muulloin+"</br>";
    }
    else {
	kortti.innerHTML += '<p>'+data.erikois+"</p>";
    }
    kortti.setAttribute( "onClick", "javascript: nayta_yohyokkays(this,2);" );
    return kortti;
}

var piirra_yohyokkaysextrakortti = function(data) {
    kortti = piirra_yohyokkayskortti(data);
    kortti.setAttribute( "onClick", "javascript: siirra_seuraavaan(this,2);" );
    return kortti;
}


var piirra_aseapukortti = function(data) {
    kortti = piirra_yohyokkayskortti(data);
    kortti.setAttribute( "onClick", "javascript: siirra_aseapupoydalle(this,2);" );
    return kortti;
}

let korruptio_shuffled = korruptio
    .map(value => ({ value, sort: Math.random() }))
    .sort((a, b) => a.sort - b.sort)
    .map(({ value }) => value)

korruptio_shuffled.forEach( function(data) {
    //data = JSON.parse(data);
    console.log(data);
    kortti = piirra_korruptiokortti(data);
    document.querySelector("#korruptiopakka").append(kortti); });


//var vastarinta = JSON.parse(vastarinta);
let vastarinta_shuffled = vastarinta
    .map(value => ({ value, sort: Math.random() }))
    .sort((a, b) => a.sort - b.sort)
    .map(({ value }) => value)

vastarinta_shuffled = vastarinta_shuffled.slice(0,12)

vastarinta_shuffled.forEach( function(data) {
    //data = JSON.parse(data);
    console.log(data);
    kortti = piirra_vastarintakortti(data);
    document.querySelector("#vastarintapakka").append(kortti); });

//var ryosto_maaseutu = JSON.parse(ryosto_maaseutu);
let ryosto_maaseutu_shuffled = ryosto_maaseutu
    .map(value => ({ value, sort: Math.random() }))
    .sort((a, b) => a.sort - b.sort)
    .map(({ value }) => value)

ryosto_maaseutu_shuffled.forEach( function(data) {
    //data = JSON.parse(data);
    //console.log(data);
    kortti = piirra_ryostokortti(data);
    document.querySelector("#ryosto_maaseutupakka").append(kortti); });

//var ryosto_kaupunki = JSON.parse(ryosto_kaupunki);
let ryosto_kaupunki_shuffled = ryosto_kaupunki
    .map(value => ({ value, sort: Math.random() }))
    .sort((a, b) => a.sort - b.sort)
    .map(({ value }) => value)

ryosto_kaupunki_shuffled.forEach( function(data) {
    //data = JSON.parse(data);
    //console.log(data);
    kortti = piirra_ryostokortti(data);
    document.querySelector("#ryosto_kaupunkipakka").append(kortti); });


let yohyokkays_shuffled = yohyokkays
    .map(value => ({ value, sort: Math.random() }))
    .sort((a, b) => a.sort - b.sort)
    .map(({ value }) => value)

yohyokkays_extra = yohyokkays_shuffled.slice(7)
yohyokkays_shuffled = yohyokkays_shuffled.slice(0,7)

yohyokkays_shuffled.forEach( function(data) {
    //data = JSON.parse(data);
    //console.log(data);
    kortti = piirra_yohyokkayskortti(data);
    document.querySelector("#yohyokkayspakka").append(kortti); });


yohyokkays_extra.forEach( function(data) {
    //data = JSON.parse(data);
    //console.log(data);
    kortti = piirra_yohyokkaysextrakortti(data);
    document.querySelector("#yohyokkays_extrapakka").append(kortti); });



//var aseapu = JSON.parse(aseapu);
let aseapu_shuffled = aseapu
    .map(value => ({ value, sort: Math.random() }))
    .sort((a, b) => a.sort - b.sort)
    .map(({ value }) => value)

aseapu_shuffled.forEach( function(data) {
    //data = JSON.parse(data);
    //console.log(data);
    kortti = piirra_aseapukortti(data);
    document.querySelector("#aseapupakka").append(kortti); });


