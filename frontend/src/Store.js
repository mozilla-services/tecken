import { extendObservable } from 'mobx'

class Store {
  constructor() {
    extendObservable(this, {
      currentUser: null,
      signOutUrl: null,
    })
  }
}

const store = (window.store = new Store())

export default store
