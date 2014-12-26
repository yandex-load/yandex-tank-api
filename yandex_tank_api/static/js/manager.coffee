app = angular.module("ng-tank-manager", ['ui.ace'])

app.controller "TankManager", ($scope, $interval, $http) ->
  updateStatus = () ->
    $http.get("status").success (data) ->
      $scope.status = data
      if $scope.current_session?
        $scope.session_status = data['$scope.current_session'].current_stage

  $scope.runTest = () ->
    $http.post("run", $scope.tankConfig).success (data) ->
      $scope.reply = data
      $scope.current_test = data.test
      $scope.current_session = data.session

  $scope.stopTest = () ->
    $http.post("stop", $scope.current_session).success (data) ->
      $scope.reply = data

  $interval(updateStatus, 1000)
