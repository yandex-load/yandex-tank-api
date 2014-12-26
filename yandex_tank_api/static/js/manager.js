(function() {
  var app;

  app = angular.module("ng-tank-manager", ['ui.ace']);

  app.controller("TankManager", function($scope, $element, $interval) {
    var updateStatus;
    updateStatus = function() {
      return $http.get("status").success(function(data) {
        return $scope.status = data;
      });
    };
    return $interval(updateStatus, 1000);
  });

}).call(this);
