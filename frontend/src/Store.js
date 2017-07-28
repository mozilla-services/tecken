import { action, extendObservable } from 'mobx'

class Store {
  constructor() {
    extendObservable(this, {
      currentUser: null,
      signInUrl: null,
      signOutUrl: null,
      fetchError: null,
      notificationMessage: null,
      redirectTo: null,
      apiRequests: [],
      resetApiRequests: action(() => {
        this.apiRequests = []
      }),
      setRedirectTo: action((destination, message = null) => {
        if (typeof destination === 'string') {
          destination = {
            pathname: destination,
          }
        }
        // console.log('typeof destination:', typeof destination);
        this.redirectTo = destination
        if (message) {
          if (typeof message === 'string') {
            this.notificationMessage = {
              message: message,
              warning: true,
            }
          } else {
            this.notificationMessage = message
          }
        }
      }),
      resetRedirectTo: action(() => {
        this.redirectTo = null
      }),
      get hasPermission() {
        return perm => {
          return (
            this.currentUser &&
            (this.currentUser.is_superuser ||
              this.currentUser.permissions.contains(perm))
          )
        }
      }
    })
  }
}

const store = (window.store = new Store())

export default store
