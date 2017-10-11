import React from 'react'
import { Link } from 'react-router-dom'
// import Fetch from './Fetch'
import store from './Store'
//
// import {
//   Loading,
//   Pagination,
//   TableSubTitle,
//   ShowValidationErrors
// } from './Common'

class Downloads extends React.PureComponent {
  constructor(props) {
    super(props)
    this.state = {
      pageTitle: 'Downloads',
      // loading: true,
      // downloads: null,
      // total: null,
      // batchSize: null,
      // apiUrl: null,
      // filter: {},
      // validationErrors: null,
    }
  }

  componentDidMount() {
    document.title = this.state.pageTitle
    store.resetApiRequests()
  }

  render() {
    return <div>
      <h1 className="title">{this.state.pageTitle}</h1>
      <Link to="/downloads/missing">Downloads Missing</Link>
    </div>
  }
}

export default Downloads
