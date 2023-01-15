function getCardElement(id, title, content, back) {
  const card = document.createElement('div');
  card.classList.add('card');
  card.innerHTML = `
    <div class="card__flipper">
      <div class="card__front">
        <div class="id">${id}</div>
        <h4 class="title">${title}</h4>
        <div class="content">${content}</div>
      </div>
      <div class="card__back">
        <span>${back}</span>
      </div>
    </div>`;
  return card;
}


var siirra_seuraavaan = function (el, i) {
  console.log('from', el.parentElement.id, 'to', el.parentElement.parentElement.children[i].id);
  el.parentElement.parentElement.children[i].appendChild(el);
  window.setTimeout(function () { el.classList.remove('card--added') }, 1);
  if (i < 3) {
    el.setAttribute("onClick", "javascript: siirra_seuraavaan(this," + (i + 1) + ");");
  } else {
    el.setAttribute("onClick", "");
  }
}

var siirra_aseapupoydalle = function (el, i) {
  console.log('from', el.parentElement.id, 'to', el.parentElement.parentElement.children[i].id);
  el.parentElement.parentElement.children[i].appendChild(el);
  window.setTimeout(function () { el.classList.remove('card--added') }, 1);
  if (i < 3) {
    el.setAttribute("onClick", "javascript: siirra_yohyokkayksiin(this," + (i + 1) + ");");
  } else {
    el.setAttribute("onClick", "");
  }
}


var nayta_vastarinta = function (el, elid) {
  const clickableElem = el.parentElement.querySelector('.card:not(.card--reveal)');
  if (el === clickableElem) {
    el.classList.add("card--reveal");
    el.removeAttribute("onClick");
  } else {
    console.log('Wrong card clicked, ignoring');
  }
}

var nayta_yohyokkays = function (el, elid) {
  el.classList.add("card--peek");
  el.setAttribute("onClick", "javascript: siirra_seuraavaan(this,2);");
  setTimeout(function () {
    console.log(el);
    if (el.classList.contains("card--peek")) {
      el.classList.remove("card--peek");
      el.setAttribute("onClick", "javascript: nayta_yohyokkays(this);");
    }
  }, 20000)
}


var siirra_yohyokkayksiin = function (el) {
  //console.log('from', el.parent.id);
  el.classList.add('card');
  el.classList.remove("card--peek");
  el.querySelector('.card__back span').innerText = 'Yöhyökkäys';
  pakka = document.querySelector("#yohyokkayspakka");

  randomposition = Math.floor(Math.random() * pakka.children.length)
  if (randomposition == pakka.children.length1 - 1) {
    console.log('Appending aseapu at position ' + randomposition);
    pakka.appendChild(el);
  }
  else {
    console.log('Inserting aseapu before position ' + (randomposition + 1));
    pakka.insertBefore(el, pakka.children[randomposition + 1])
  }
  el.setAttribute("onClick", "javascript: nayta_yohyokkays(this);");

  // sekoita yohyokkays:
  //for (var i = pakka.children.length; i >= 0; i--) {
  //	pakka.appendChild(ul.children[Math.random() * i | 0]);
  //}
}




// Piirretaan!

var piirra_korruptiokortti = function (data) {
  const kortti = getCardElement(
    data.id,
    data.mita,
    `
    <div class="ohje">${data.ohje}</div>
    <div class="paljonko">${data.paljonko}</div>
    `,
    'Ennakkokorruptio'
  );
  kortti.setAttribute("onClick", "javascript: siirra_seuraavaan(this,2);");
  kortti.classList.add('card--added');
  return kortti;
}


var piirra_vastarintakortti = function (data) {
  const kortti = getCardElement(
    data.id,
    data.maasto,
    `
      <p>Kesto:${data.kesto}</p>
      <p>Hyökkäys: Jos <b>${data.Jos}:</b>${data.niin}</p>
      <p>Muuten:${data.muuten}</br>
      <p>Ryöstettävää:${data.ryostettavaa}</br>
    `,
    'Vastarinta'
  );
  // kortti.setAttribute("onClick", "javascript: siirra_seuraavaan(this,2);");
  kortti.setAttribute("onClick", "javascript: nayta_vastarinta(this,2);");
  kortti.classList.add('card--added');
  return kortti;
}

var piirra_ryostokortti = function (data, back) {
  const kortti = getCardElement(
    data.id,
    data.paikka,
    `
      <p>Jos <b>${data.Jos}:</b> ${data.niin}</p>
      <p>Muuten: ${data.muulloin}</p>
    `,
    back
  );
  kortti.setAttribute("onClick", "javascript: siirra_seuraavaan(this,2);");
  kortti.classList.add('card--added');
  return kortti;
}

var piirra_yohyokkayskortti = function (data, back) {
  let content = '';
  if (data.erikois == '') {
    content += `
      <p>Kohde:${data.kohde}</p>
      <p>Hyökkäys: Jos <b>${data.jos}:</b> ${data.niin}</p>
      <p>Muuten:${data.muulloin}</br>
    `;
  }
  else {
    content = `<p>${data.erikois}</p>`;
  }

  const kortti = getCardElement(
    data.id,
    data.nimi,
    content,
    back
  );

  kortti.setAttribute("onClick", "javascript: nayta_yohyokkays(this,2);");
  kortti.classList.add('card--added');
  return kortti;
}

var piirra_yohyokkaysextrakortti = function (data) {
  kortti = piirra_yohyokkayskortti(data, 'Yöhyökkäys extrat');
  kortti.setAttribute("onClick", "javascript: siirra_seuraavaan(this,2);");
  return kortti;
}


var piirra_aseapukortti = function (data) {
  kortti = piirra_yohyokkayskortti(data, 'Ulkomainen aseapu');
  kortti.setAttribute("onClick", "javascript: siirra_aseapupoydalle(this,2);");
  return kortti;
}

let korruptio_shuffled = korruptio
  .map(value => ({ value, sort: Math.random() }))
  .sort((a, b) => a.sort - b.sort)
  .map(({ value }) => value)

korruptio_shuffled.forEach(function (data) {
  //data = JSON.parse(data);
  console.log(data);
  kortti = piirra_korruptiokortti(data);
  document.querySelector("#korruptiopakka").append(kortti);
});


//var vastarinta = JSON.parse(vastarinta);
let vastarinta_shuffled = vastarinta
  .map(value => ({ value, sort: Math.random() }))
  .sort((a, b) => a.sort - b.sort)
  .map(({ value }) => value)

vastarinta_shuffled = vastarinta_shuffled.slice(0, 12)

vastarinta_shuffled.forEach(function (data) {
  //data = JSON.parse(data);
  console.log(data);
  kortti = piirra_vastarintakortti(data);
  document.querySelector("#vastarintapoyta").append(kortti);
});

//var ryosto_maaseutu = JSON.parse(ryosto_maaseutu);
let ryosto_maaseutu_shuffled = ryosto_maaseutu
  .map(value => ({ value, sort: Math.random() }))
  .sort((a, b) => a.sort - b.sort)
  .map(({ value }) => value)

ryosto_maaseutu_shuffled.forEach(function (data) {
  //data = JSON.parse(data);
  //console.log(data);
  kortti = piirra_ryostokortti(data, 'Ryöstettävää: Maaseutu');
  document.querySelector("#ryosto_maaseutupakka").append(kortti);
});

//var ryosto_kaupunki = JSON.parse(ryosto_kaupunki);
let ryosto_kaupunki_shuffled = ryosto_kaupunki
  .map(value => ({ value, sort: Math.random() }))
  .sort((a, b) => a.sort - b.sort)
  .map(({ value }) => value)

ryosto_kaupunki_shuffled.forEach(function (data) {
  //data = JSON.parse(data);
  //console.log(data);
  kortti = piirra_ryostokortti(data, 'Ryöstettävää: Kaupunki');
  document.querySelector("#ryosto_kaupunkipakka").append(kortti);
});


let yohyokkays_shuffled = yohyokkays
  .map(value => ({ value, sort: Math.random() }))
  .sort((a, b) => a.sort - b.sort)
  .map(({ value }) => value)

yohyokkays_extra = yohyokkays_shuffled.slice(7)
yohyokkays_shuffled = yohyokkays_shuffled.slice(0, 7)

yohyokkays_shuffled.forEach(function (data) {
  //data = JSON.parse(data);
  //console.log(data);
  kortti = piirra_yohyokkayskortti(data, 'Yöhyökkäys');
  document.querySelector("#yohyokkayspakka").append(kortti);
});


yohyokkays_extra.forEach(function (data) {
  //data = JSON.parse(data);
  //console.log(data);
  kortti = piirra_yohyokkaysextrakortti(data);
  document.querySelector("#yohyokkays_extrapakka").append(kortti);
});



//var aseapu = JSON.parse(aseapu);
let aseapu_shuffled = aseapu
  .map(value => ({ value, sort: Math.random() }))
  .sort((a, b) => a.sort - b.sort)
  .map(({ value }) => value)

aseapu_shuffled.forEach(function (data) {
  //data = JSON.parse(data);
  //console.log(data);
  kortti = piirra_aseapukortti(data);
  document.querySelector("#aseapupakka").append(kortti);
});


